"""Real-time intent extraction with subtle signal detection.

Beyond basic intent categories, this also catches:
- Half-truths and deflection patterns
- Avoidance markers
- Signs of real distress vs performative complaint
- Likely lies (vague answers to specific questions)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings


class IntentType(str, Enum):
    PROMISE_TO_PAY = "promise_to_pay"
    HARDSHIP = "hardship"
    AFFORDABILITY = "affordability"
    DISPUTE = "dispute"
    DISTRESS = "distress"
    AVOIDANCE = "avoidance"
    COOPERATIVE = "cooperative"
    NONE = "none"


class HardshipKind(str, Enum):
    JOB_LOSS = "job_loss"
    MEDICAL = "medical"
    FAMILY_EMERGENCY = "family_emergency"
    SALARY_DELAY = "salary_delay"
    BUSINESS_LOSS = "business_loss"
    OTHER = "other"
    NONE = "none"


class IntentSignal(BaseModel):
    """One structured read on the most recent borrower turn."""

    intent: IntentType = Field(description="Primary intent of the borrower's last message")

    confidence: float = Field(ge=0.0, le=1.0)

    promised_amount: Optional[int] = Field(default=None)
    promised_date: Optional[str] = Field(default=None)

    hardship_kind: HardshipKind = Field(default=HardshipKind.NONE)

    distress_level: int = Field(default=0, ge=0, le=100)

    keywords: list[str] = Field(default_factory=list)

    # NEW: Subtle signals
    is_deflecting: bool = Field(
        default=False,
        description="Borrower gave a vague non-answer to a direct question",
    )
    seems_truthful: bool = Field(
        default=True,
        description="Story is coherent and specific. False if details contradict or are too vague.",
    )
    real_hardship: bool = Field(
        default=False,
        description="Specific, verifiable-sounding hardship (named hospital, employer, dates) vs generic complaint.",
    )
    needs_human: bool = Field(
        default=False,
        description="Situation requires human escalation (legal dispute, suicidal language, complex grievance).",
    )

    # NEW: Conversation advancement
    advances_conversation: bool = Field(
        default=True,
        description="Does this turn move the conversation forward, or are they stuck/looping?",
    )


_EXTRACTION_PROMPT = """\
You are an intent classifier for an AI loan-recovery agent. Read the
borrower's most recent message and classify it into a structured signal.

# Intent rules
- COOPERATIVE: engaged, willing to discuss, looking for solutions.
- PROMISE_TO_PAY: specific amount + specific date committed.
- AFFORDABILITY: open to paying, but partial or delayed.
- HARDSHIP: facing a real life event (job loss, medical, etc.). Specify kind.
- DISPUTE: claims they already paid, or amount is wrong.
- DISTRESS: panic, crying, suicidal hints, severe agitation. Distress >= 70.
- AVOIDANCE: deflecting, vague answers to direct questions, "not now".
- NONE: small talk, unclear, or off-topic.

# Subtle signal rules
- is_deflecting=true if they answer a direct question with vagueness or
  change subject. Example: Aria asks "When can you pay?" → borrower says
  "I'll see, things are tough" → is_deflecting=true.
- seems_truthful=false if details are inconsistent across the conversation
  or implausibly vague.
- real_hardship=true ONLY for specific claims (named hospital, named
  employer, specific date of layoff, etc.). Generic "things are bad" is false.
- needs_human=true for: legal disputes, suicidal language, demands for
  manager, complex grievances.
- advances_conversation=false if borrower is repeating themselves OR
  giving the same non-answer they gave before.

# Distress scale
- 0-30: calm
- 30-60: stressed but holding it together
- 60-80: clear distress (raised voice, pleading, desperation)
- 80-100: severe distress (crying, suicidal hints, panic)

When in doubt, prefer NONE over guessing.

Borrower message:
\"\"\"
{utterance}
\"\"\"

Recent conversation context (most recent last):
\"\"\"
{context}
\"\"\"
"""


class IntentExtractor:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        self._model = get_settings().openai_model

    async def extract(self, utterance: str, context: str = "") -> IntentSignal:
        """Run a structured-output call to classify a single borrower turn."""
        try:
            response = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "You return only structured intent signals.",
                    },
                    {
                        "role": "user",
                        "content": _EXTRACTION_PROMPT.format(
                            utterance=utterance.strip(),
                            context=context.strip() or "(start of call)",
                        ),
                    },
                ],
                response_format=IntentSignal,
                temperature=0.1,
            )

            parsed = response.choices[0].message.parsed
            if parsed is None:
                return IntentSignal(intent=IntentType.NONE, confidence=0.0)
            return parsed
        except Exception:
            # Fallback if structured parse fails
            return IntentSignal(intent=IntentType.NONE, confidence=0.0)
