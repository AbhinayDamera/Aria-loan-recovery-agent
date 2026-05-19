"""Aria's brain — multi-stage reasoning agent.

Per turn:
  Stage 1 (parallel) — Intent extraction + Memory update
  Stage 2 — Personality mode selection
  Stage 3 — Response generation with full context
  Stage 4 — Compliance validation (auto-rewrite if violation)
  Stage 5 — Anti-repeat check
  Publish to dashboard, return to TTS

All stages are logged to the dashboard so judges can SEE Aria thinking.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from app.compliance import COMPLIANCE_RULES_BLOCK, ComplianceValidator
from app.config import get_settings
from app.conversation import DEMO_BORROWER, BorrowerContext, render_full_prompt
from app.events import Event, EventType, event_bus
from app.intent_extractor import IntentExtractor, IntentSignal, IntentType
from app.memory import MemoryManager
from app.personality import PersonalityState, render_mode_block, select_mode


@dataclass
class Turn:
    role: str  # "system" | "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


class AgentBrain:
    """Per-call multi-stage reasoning agent."""

    def __init__(self, call_id: str, borrower: Optional[BorrowerContext] = None) -> None:
        self.call_id = call_id
        self.borrower = borrower or DEMO_BORROWER

        cfg = get_settings()
        self._client = AsyncOpenAI(api_key=cfg.openai_api_key)
        self._model = cfg.openai_model

        self._intent = IntentExtractor()
        self._memory = MemoryManager(call_id)
        self._validator = ComplianceValidator()

        # State
        self._history: list[Turn] = []
        self._recent_responses: list[str] = []  # for anti-repeat
        self._last_aria_text: str = ""
        self._closed = False
        self._call_started_published = False

    # ─── Public API ──────────────────────────────────────────

    async def opening_line(self) -> str:
        """First thing Aria says when call connects."""
        line = (
            f"Hi {self.borrower.borrower_name}, I'm Aria, an AI assistant from "
            f"{self.borrower.lender_name}. This call may be recorded for quality. "
            f"Is now a good time to talk?"
        )
        self._history.append(Turn(role="assistant", content=line))
        self._last_aria_text = line
        self._recent_responses.append(line)

        await self._publish_call_started()
        await self._publish_transcript("aria", line)
        await self._publish_thinking_step("Greeting", "Opening with disclosure (RBI required)")

        return line

    async def respond(self, user_text: str) -> str:
        """Process borrower utterance through multi-stage reasoning chain."""
        if self._closed:
            return ""

        user_text = user_text.strip()
        if not user_text:
            return ""

        self._history.append(Turn(role="user", content=user_text))
        await self._publish_transcript("borrower", user_text)

        # ─── Fast-path detection ──────────────────────────────
        # Tiny utterances ("yes", "ok", "hmm") don't need full
        # intent/memory analysis. Skip those LLM calls.
        word_count = len(user_text.split())
        is_tiny = word_count <= 3

        # ─── Stage 1: Intent extraction (parallel with memory update) ───

        await self._publish_thinking_step("Analyzing", "Extracting intent and emotion")

        recent_context = self._build_recent_context()

        if is_tiny:
            # Skip the LLM calls — use defaults
            intent_signal = IntentSignal(
                intent=IntentType.COOPERATIVE if user_text.lower() in {"yes", "yeah", "ok", "okay", "sure"} else IntentType.NONE,
                confidence=0.5,
            )
            memory_state = self._memory.memory
        else:
            intent_task = asyncio.create_task(
                self._intent.extract(user_text, recent_context)
            )
            memory_task = asyncio.create_task(
                self._memory.update_after_turn(self._last_aria_text, user_text)
            )

            try:
                intent_signal, memory_state = await asyncio.gather(intent_task, memory_task)
            except Exception as e:
                logger.error(f"[{self.call_id}] Stage 1 error: {e}")
                intent_signal = IntentSignal(intent=IntentType.NONE, confidence=0.0)
                memory_state = self._memory.memory

        # Publish intent + emotion
        await event_bus.publish(
            Event(
                type=EventType.INTENT,
                call_id=self.call_id,
                payload=intent_signal.model_dump(),
            )
        )
        await event_bus.publish(
            Event(
                type=EventType.EMOTION,
                call_id=self.call_id,
                payload={"score": intent_signal.distress_level},
            )
        )

        # ─── Stage 2: Personality mode selection ──────────────

        personality = select_mode(
            distress_level=intent_signal.distress_level,
            intent=intent_signal.intent.value,
            repeat_promise_count=memory_state.repeat_promise_count,
            avoidance_count=memory_state.avoidance_count,
            has_real_hardship=intent_signal.real_hardship,
        )

        await self._publish_thinking_step(
            "Personality",
            f"Mode: {personality.mode.value.upper()} ({personality.reason})",
        )

        await event_bus.publish(
            Event(
                type=EventType.INTENT,  # reuse intent channel for personality
                call_id=self.call_id,
                payload={
                    "personality_mode": personality.mode.value,
                    "personality_reason": personality.reason,
                },
            )
        )

        # ─── Auto-escalation check ────────────────────────────

        if (
            intent_signal.needs_human
            or intent_signal.distress_level >= get_settings().distress_threshold
            or intent_signal.intent == IntentType.DISTRESS
        ):
            await event_bus.publish(
                Event(
                    type=EventType.ESCALATION,
                    call_id=self.call_id,
                    payload={
                        "reason": intent_signal.intent.value,
                        "score": intent_signal.distress_level,
                        "needs_human": intent_signal.needs_human,
                    },
                )
            )

        # PTP capture
        if intent_signal.intent == IntentType.PROMISE_TO_PAY and intent_signal.promised_amount:
            await event_bus.publish(
                Event(
                    type=EventType.PTP_CAPTURED,
                    call_id=self.call_id,
                    payload={
                        "amount": intent_signal.promised_amount,
                        "promised_for": intent_signal.promised_date,
                    },
                )
            )

        # ─── Stage 3: Response generation ─────────────────────

        await self._publish_thinking_step("Composing", "Generating compassionate response")

        reply = await self._generate_reply(
            user_text=user_text,
            intent=intent_signal,
            personality=personality,
            memory_state=memory_state,
        )

        # ─── Stage 4: Compliance validation ───────────────────

        compliance = self._validator.validate(reply)
        if not compliance.is_compliant:
            logger.warning(
                f"[{self.call_id}] Compliance violation: {compliance.violations}"
            )
            await self._publish_thinking_step(
                "Compliance",
                f"Auto-correcting: {', '.join(compliance.violations[:1])}",
            )
            reply = compliance.suggested_alternative or reply
        else:
            await self._publish_thinking_step("Compliance", "✓ RBI Fair Practices")

        # ─── Stage 5: Anti-repeat ─────────────────────────────

        if self._is_repeating(reply):
            logger.info(f"[{self.call_id}] Detected repeat. Regenerating.")
            await self._publish_thinking_step("Anti-repeat", "Reframing to advance conversation")
            reply = await self._regenerate_to_advance(
                user_text=user_text,
                intent=intent_signal,
                personality=personality,
                memory_state=memory_state,
                previous_reply=reply,
            )

        # ─── Finalize ─────────────────────────────────────────

        self._history.append(Turn(role="assistant", content=reply))
        self._last_aria_text = reply
        self._recent_responses.append(reply)
        if len(self._recent_responses) > 5:
            self._recent_responses = self._recent_responses[-5:]

        await self._publish_transcript("aria", reply)

        return reply

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await event_bus.publish(
            Event(
                type=EventType.CALL_ENDED,
                call_id=self.call_id,
                payload={
                    "turns": len(self._history),
                    "memory": self._memory.memory.model_dump(),
                },
            )
        )

    # ─── Internal helpers ────────────────────────────────────

    async def _generate_reply(
        self,
        *,
        user_text: str,
        intent: IntentSignal,
        personality: PersonalityState,
        memory_state,
    ) -> str:
        """Generate Aria's reply using full context."""
        # Compose full system prompt for this turn
        prompt = render_full_prompt(
            base_context=self.borrower.base_context(),
            compliance_block=COMPLIANCE_RULES_BLOCK,
            personality_block=render_mode_block(personality),
            memory_block=memory_state.render(),
        )

        # Add conversation history
        messages = [{"role": "system", "content": prompt}]

        # Recent turns only (keep prompt size sane)
        for turn in self._history[-10:]:
            if turn.role in ("user", "assistant"):
                messages.append({"role": turn.role, "content": turn.content})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=0.7,
                max_tokens=45,  # ~25-30 words; shorter = faster TTS + snappier feel
            )
            reply = (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"[{self.call_id}] LLM error: {e}")
            return "I'm sorry, could you say that again?"

        if not reply:
            return "I didn't quite catch that, sir. Could you repeat?"

        return reply

    async def _regenerate_to_advance(
        self,
        *,
        user_text: str,
        intent: IntentSignal,
        personality: PersonalityState,
        memory_state,
        previous_reply: str,
    ) -> str:
        """Regenerate reply, explicitly avoiding repetition."""
        anti_repeat = (
            "# CRITICAL — Anti-repeat directive\n"
            f"Your previous response was: \"{previous_reply}\"\n"
            f"Other recent responses: {self._recent_responses[-3:]}\n\n"
            "DO NOT repeat the same idea. Instead, advance the conversation by:\n"
            "- Asking a more specific question\n"
            "- Offering a concrete restructuring option\n"
            "- Acknowledging the loop and asking what would actually help"
        )

        prompt = render_full_prompt(
            base_context=self.borrower.base_context(),
            compliance_block=COMPLIANCE_RULES_BLOCK,
            personality_block=render_mode_block(personality),
            memory_block=memory_state.render(),
            anti_repeat_hint=anti_repeat,
        )

        messages = [{"role": "system", "content": prompt}]
        for turn in self._history[-10:]:
            if turn.role in ("user", "assistant"):
                messages.append({"role": turn.role, "content": turn.content})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=0.85,  # higher for variation
                max_tokens=80,
            )
            return (response.choices[0].message.content or previous_reply).strip()
        except Exception:
            return previous_reply

    def _is_repeating(self, reply: str) -> bool:
        """Check if this reply is too similar to recent ones."""
        if not self._recent_responses:
            return False

        # Simple word-overlap check
        reply_words = set(reply.lower().split())
        for prev in self._recent_responses[-2:]:
            prev_words = set(prev.lower().split())
            if not prev_words:
                continue
            overlap = len(reply_words & prev_words) / max(len(reply_words), 1)
            if overlap > 0.85:  # raised from 0.7 — only true near-duplicates
                return True
        return False

    def _build_recent_context(self) -> str:
        """Build a short conversation snippet for intent classification."""
        recent = self._history[-6:]
        return "\n".join(
            f"{t.role}: {t.content}"
            for t in recent
            if t.role in ("user", "assistant")
        )

    # ─── Publishing helpers ──────────────────────────────────

    async def _publish_call_started(self) -> None:
        if self._call_started_published:
            return
        self._call_started_published = True
        await event_bus.publish(
            Event(
                type=EventType.CALL_STARTED,
                call_id=self.call_id,
                payload={
                    "borrower_id": self.borrower.borrower_id,
                    "borrower_name": self.borrower.borrower_name,
                    "overdue_amount": self.borrower.overdue_amount,
                    "days_overdue": self.borrower.days_overdue,
                    "emi_amount": self.borrower.emi_amount,
                    "history_notes": self.borrower.history_notes,
                },
            )
        )

    async def _publish_transcript(self, role: str, text: str) -> None:
        await event_bus.publish(
            Event(
                type=EventType.TRANSCRIPT,
                call_id=self.call_id,
                payload={"role": role, "text": text},
            )
        )

    async def _publish_thinking_step(self, label: str, detail: str) -> None:
        """Show Aria's reasoning step on the dashboard (live agent thinking)."""
        await event_bus.publish(
            Event(
                type=EventType.INTENT,
                call_id=self.call_id,
                payload={"thinking_label": label, "thinking_detail": detail},
            )
        )