"""Conversation memory — beyond raw turn history.

Maintains a structured summary of the call that Aria reads each turn
to know what's been promised, contested, and avoided. This makes Aria
sound like she's actually following the conversation, not just
generating from the last message.

Updated incrementally each turn via a small LLM call (cheap).
"""

from __future__ import annotations

from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings


class CallMemory(BaseModel):
    """Structured summary of the call so far."""

    promises_made: list[str] = Field(
        default_factory=list,
        description="Specific commitments the borrower stated (amount, date)",
    )
    concerns_raised: list[str] = Field(
        default_factory=list,
        description="Hardships, problems, life events the borrower shared",
    )
    questions_asked: list[str] = Field(
        default_factory=list,
        description="Direct questions the borrower asked Aria",
    )
    topics_avoided: list[str] = Field(
        default_factory=list,
        description="Topics where the borrower deflected or gave vague answers",
    )
    emotional_arc: list[str] = Field(
        default_factory=list,
        description="Emotional state over time (calm, anxious, distressed)",
    )
    current_focus: str = Field(
        default="",
        description="What this part of the conversation is about right now",
    )

    # Counters Aria uses for personality decisions
    repeat_promise_count: int = 0
    avoidance_count: int = 0

    def render(self) -> str:
        """Format the memory for injection into Aria's prompt."""
        lines = []

        if self.current_focus:
            lines.append(f"## What this conversation is about right now\n{self.current_focus}")

        if self.promises_made:
            lines.append("## What the borrower has promised")
            for p in self.promises_made[-5:]:
                lines.append(f"- {p}")

        if self.concerns_raised:
            lines.append("## Concerns the borrower has shared")
            for c in self.concerns_raised[-5:]:
                lines.append(f"- {c}")

        if self.questions_asked:
            lines.append("## Questions the borrower has asked")
            for q in self.questions_asked[-3:]:
                lines.append(f"- {q}")

        if self.topics_avoided:
            lines.append("## Topics the borrower has avoided")
            for t in self.topics_avoided[-3:]:
                lines.append(f"- {t}")

        if not lines:
            return "(start of call — no memory yet)"

        return "\n".join(lines)


_UPDATE_PROMPT = """\
You are maintaining a structured memory of a phone call between an AI
loan-recovery agent and a borrower. Read the latest turn and update the
memory.

# Rules
- Only add NEW information. Don't repeat what's already there.
- Be specific: "promised ₹2000 by Friday" not "said something about money".
- topics_avoided means the borrower deflected or gave a non-answer.
- emotional_arc gets one new word per update: calm/anxious/distressed/relieved/angry.
- current_focus describes what THIS PART of the call is about (e.g., "discussing job loss").
- Increment repeat_promise_count if borrower restates a previously broken promise.
- Increment avoidance_count if borrower deflects from a direct question.

# Current memory
{current_memory}

# Latest exchange
Aria: {aria_text}
Borrower: {borrower_text}

Return the FULL updated memory (not just the delta).
"""


class MemoryManager:
    """Updates and serves the call memory."""

    def __init__(self, call_id: str) -> None:
        self.call_id = call_id
        self._memory = CallMemory()
        self._client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        self._model = get_settings().openai_model

    @property
    def memory(self) -> CallMemory:
        return self._memory

    async def update_after_turn(self, aria_text: str, borrower_text: str) -> CallMemory:
        """Run a structured-output call to update the memory."""
        try:
            current_json = self._memory.model_dump_json()
            response = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "You return only updated CallMemory objects.",
                    },
                    {
                        "role": "user",
                        "content": _UPDATE_PROMPT.format(
                            current_memory=current_json,
                            aria_text=aria_text,
                            borrower_text=borrower_text,
                        ),
                    },
                ],
                response_format=CallMemory,
                temperature=0.0,
            )
            parsed = response.choices[0].message.parsed
            if parsed is not None:
                self._memory = parsed
        except Exception:
            # If memory update fails, keep the old memory (don't break call)
            pass

        return self._memory
