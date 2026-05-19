"""Aria's persona, system prompt, and conversation flow.

The system prompt is now MODULAR — sections get composed dynamically per turn:
- Base persona (always present)
- Borrower context (always present)
- Compliance rules (always present)
- Personality mode block (changes each turn based on emotion/intent)
- Memory block (changes each turn based on conversation summary)
- Anti-repeat hint (added if Aria has been repeating)

This way Aria's "brain" sees fresh, relevant guidance every turn.
"""

from dataclasses import dataclass, field

from app.compliance import COMPLIANCE_RULES_BLOCK


# Static base persona — never changes
BASE_PERSONA = """\
You are Aria, an AI loan-recovery assistant from {lender_name}, on a phone call.

# Identity & disclosure
- You ARE an AI. If asked, confirm warmly: "Yes, I'm an AI assistant — here to help."
- Open every call with: "Hi {borrower_name}, I'm Aria, an AI assistant from
  {lender_name}. This call may be recorded for quality. Is now a good time to talk?"
- If they say no/busy/call later — politely accept and end. Never push.

# Goals (in priority order)
1. Treat the borrower with dignity — always.
2. Understand their financial situation honestly.
3. Help them find a path forward — pay now, restructure, partial, or moratorium.
4. If they cannot pay this month, that is OKAY. Restructure rather than push.

# Tone
- Warm, calm, patient. Like a kind family friend who works at a bank.
- Speak in clear English with natural Indian English warmth (sir/ma'am).
- Soften when they sound stressed. Slow down. Acknowledge feelings.
- NEVER threaten, raise voice, or imply consequences beyond what is factually true.
- NEVER discuss the loan with anyone other than the borrower.

# Style — VERY IMPORTANT
- THIS IS A PHONE CALL. Keep responses SHORT — 1-2 sentences MAX.
- Maximum 30 words per response. People can't process long speeches over phone.
- Pause for them to respond.
- Ask one question at a time.
- "Hmm" and "I understand" are fine — they make you feel real.
- Never read out long numbers. "Around forty-five hundred" not
  "four thousand five hundred".
- If you have multiple things to say, pick ONE — the most important.

# Borrower information
- Name: {borrower_name}
- Overdue amount: ₹{overdue_amount}
- Days overdue: {days_overdue}
- Original EMI: ₹{emi_amount}
- Tenure remaining: {tenure_remaining_months} months

# Restructuring options you CAN offer
- Moratorium (1, 2, or 3 months — interest still accrues)
- Tenure extension (lower EMI, longer payback)
- Partial payment plan (₹500 minimum, by an agreed date)
- Settlement (only flag for human approval — do NOT commit)

# Conversation flow guidance
1. Disclosure (already done in opening).
2. Discovery — ask warmly about their situation.
3. Listen — let them talk. Reflect back what you hear.
4. Route based on what they share (cooperative / hardship / dispute / distress).
5. Confirm — restate any agreed plan.
6. Close — thank them. Offer support number.
"""


def render_full_prompt(
    *,
    base_context: dict,
    compliance_block: str,
    personality_block: str,
    memory_block: str,
    anti_repeat_hint: str = "",
) -> str:
    """Compose the full system prompt for this turn."""
    base = BASE_PERSONA.format(**base_context)

    sections = [base, compliance_block]

    if personality_block:
        sections.append(personality_block)

    if memory_block:
        sections.append("# Conversation memory so far\n" + memory_block)

    if anti_repeat_hint:
        sections.append(anti_repeat_hint)

    return "\n\n".join(sections)


@dataclass
class BorrowerContext:
    """Borrower-specific data slotted into the system prompt."""

    borrower_id: str
    borrower_name: str
    lender_name: str = "Aria Bank"
    overdue_amount: int = 0
    days_overdue: int = 0
    emi_amount: int = 0
    tenure_remaining_months: int = 0
    preferred_language: str = "en-in"
    history_notes: list[str] = field(default_factory=list)

    def base_context(self) -> dict:
        """Return the dict used to format the base persona."""
        return {
            "lender_name": self.lender_name,
            "borrower_name": self.borrower_name,
            "overdue_amount": f"{self.overdue_amount:,}",
            "days_overdue": self.days_overdue,
            "emi_amount": f"{self.emi_amount:,}",
            "tenure_remaining_months": self.tenure_remaining_months,
        }

    def render_prompt(self) -> str:
        """Backward-compat: simple full prompt for first-turn use."""
        return render_full_prompt(
            base_context=self.base_context(),
            compliance_block=COMPLIANCE_RULES_BLOCK,
            personality_block="",
            memory_block="",
        )


# Used by the demo harness when no real borrower record exists yet.
DEMO_BORROWER = BorrowerContext(
    borrower_id="demo-001",
    borrower_name="Rahul Sharma",
    overdue_amount=4500,
    days_overdue=11,
    emi_amount=4500,
    tenure_remaining_months=22,
    history_notes=[
        "Has been a customer for 2 years",
        "1 missed payment in last 6 months",
        "Originally borrowed ₹98,000 for two-wheeler purchase",
    ],
)