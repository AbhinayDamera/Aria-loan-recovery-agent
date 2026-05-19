"""Personality engine — picks Aria's tone based on emotion + intent signals.

Three modes:
- GENTLE: When borrower is distressed, vulnerable, or shows real hardship.
  Warm, slow, validating. Never adds pressure.
- EMPATHETIC: When borrower is cooperative but emotionally engaged.
  Active listener, validates feelings, offers concrete paths.
- FIRM: When borrower is avoiding, showing dishonesty patterns, or has
  broken multiple promises. Direct, professional, never threatening.

The mode is recomputed every turn based on the latest signals.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class PersonalityMode(str, Enum):
    GENTLE = "gentle"
    EMPATHETIC = "empathetic"
    FIRM = "firm"


# Behavioral instructions injected into the prompt for each mode.
MODE_INSTRUCTIONS: dict[PersonalityMode, str] = {
    PersonalityMode.GENTLE: """\
You are in GENTLE mode.
- Slow down. Use longer pauses (the human will hear silence as warmth).
- Lead with feelings, not solutions. "I can hear how heavy this is."
- Use phrases like: "Take your time", "There's no pressure", "I understand".
- Offer help unconditionally before asking for anything.
- Never use the word "must" or "need to". Use "could you", "would it help".
- If they bring up the loan, gently redirect to their situation first.
- Keep responses very short — 1-2 sentences max.
""",
    PersonalityMode.EMPATHETIC: """\
You are in EMPATHETIC mode.
- Mirror their energy — match their language and pace.
- Validate before responding: "That makes complete sense."
- Be a thinking partner, not a script. Help them solve their problem.
- Offer concrete options when they're ready (moratorium, partial, restructure).
- Use "we" language: "Let's see what we can work out."
- Acknowledge their effort: "Thank you for being honest about this."
- Keep it conversational — 2-3 sentences.
""",
    PersonalityMode.FIRM: """\
You are in FIRM mode.
- Be direct but never cold. Professional with warmth still underneath.
- Don't accept vague answers. Politely ask for specifics: "What date works?"
- Reference what was promised earlier if relevant.
- Do NOT threaten. Do NOT imply consequences beyond facts.
- If they keep deflecting, acknowledge it kindly: "I notice we keep coming
  back to this. Let's try to find something that actually works for you."
- Never raise voice tone — keep words measured.
- Keep it tight — 1-2 sentences.
""",
}


class PersonalityState(BaseModel):
    """Current personality state. Recomputed each turn."""

    mode: PersonalityMode
    reason: str  # short why-this-mode for dashboard display
    confidence: float = 1.0


def select_mode(
    *,
    distress_level: int,
    intent: str,
    repeat_promise_count: int,
    avoidance_count: int,
    has_real_hardship: bool,
) -> PersonalityState:
    """Pick the right personality mode for this turn.

    Decision tree:
    1. Distress >= 65 → GENTLE (vulnerability comes first)
    2. Real hardship (job loss/medical/etc.) → GENTLE
    3. Multiple broken promises or heavy avoidance → FIRM
    4. Cooperative or engaged → EMPATHETIC
    5. Default → EMPATHETIC
    """
    if distress_level >= 65:
        return PersonalityState(
            mode=PersonalityMode.GENTLE,
            reason=f"high distress ({distress_level})",
            confidence=0.95,
        )

    if has_real_hardship:
        return PersonalityState(
            mode=PersonalityMode.GENTLE,
            reason="hardship reported",
            confidence=0.9,
        )

    if intent == "distress":
        return PersonalityState(
            mode=PersonalityMode.GENTLE,
            reason="distress signal",
            confidence=0.9,
        )

    if repeat_promise_count >= 2 or avoidance_count >= 3:
        return PersonalityState(
            mode=PersonalityMode.FIRM,
            reason=f"avoidance pattern (broken={repeat_promise_count}, deflects={avoidance_count})",
            confidence=0.85,
        )

    if intent in {"cooperative", "promise_to_pay", "affordability"}:
        return PersonalityState(
            mode=PersonalityMode.EMPATHETIC,
            reason=f"engaged ({intent})",
            confidence=0.85,
        )

    # Default
    return PersonalityState(
        mode=PersonalityMode.EMPATHETIC,
        reason="default — neutral exchange",
        confidence=0.7,
    )


def render_mode_block(state: PersonalityState) -> str:
    """Build the snippet that gets injected into the system prompt this turn."""
    instructions = MODE_INSTRUCTIONS[state.mode]
    return f"""\
# Current personality mode: {state.mode.value.upper()}
# Reason: {state.reason}

{instructions}"""
