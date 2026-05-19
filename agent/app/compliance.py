"""RBI Fair Practices Code compliance.

Two layers of safety:
1. Pre-generation: rules baked into Aria's prompt (avoid coercive language).
2. Post-generation: validator scans Aria's reply BEFORE she speaks.

Reference: RBI Master Direction on Fair Practices Code for NBFCs (2007/updated)
and recent Digital Lending Guidelines (Sep 2022).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel


# Words/phrases that indicate coercive collection — explicit RBI violations
COERCIVE_PATTERNS = [
    r"\b(legal action|sue|lawsuit|court case)\b.*\b(will|going to|filing)\b",
    r"\b(seize|repossess|attach)\b.*\b(property|assets|salary)\b",
    r"\b(jail|arrest|police)\b",
    r"\b(blacklist|cibil destroyed|credit ruined)\b",
    r"\b(call your (employer|family|relatives|neighbors))\b",
    r"\bshame|disgrace|public(ly)? embarrass",
    r"\b(must|have to|need to) pay (today|now|immediately)\b",
    r"\b(no choice|no option)\b",
]

# Phrases that imply false authority/identity
IDENTITY_VIOLATIONS = [
    r"\bi am (a |an )?human\b",
    r"\bnot an? ai\b",
    r"\b(government|police|court) (officer|official|representative)\b",
]

# RBI-mandated working hours (8 AM - 8 PM IST). For demo, we mock-validate.
ALLOWED_HOURS_START = 8
ALLOWED_HOURS_END = 20


class ComplianceCheck(BaseModel):
    """Result of running compliance validation on Aria's proposed reply."""

    is_compliant: bool
    violations: list[str] = []
    severity: str = "ok"  # ok | warning | violation
    suggested_alternative: Optional[str] = None


class ComplianceValidator:
    """Validates Aria's proposed responses against RBI rules."""

    @staticmethod
    def validate(reply: str, *, call_started_hour: Optional[int] = None) -> ComplianceCheck:
        """Run all checks. Returns a ComplianceCheck with violations if any."""
        violations: list[str] = []

        lower = reply.lower()

        # 1. Coercive language
        for pattern in COERCIVE_PATTERNS:
            if re.search(pattern, lower, re.IGNORECASE):
                violations.append(f"Coercive language detected: matches /{pattern}/")

        # 2. Identity violations
        for pattern in IDENTITY_VIOLATIONS:
            if re.search(pattern, lower, re.IGNORECASE):
                violations.append(f"Identity violation: matches /{pattern}/")

        # 3. Working hours (if known)
        if call_started_hour is not None:
            if call_started_hour < ALLOWED_HOURS_START or call_started_hour >= ALLOWED_HOURS_END:
                violations.append(
                    f"Call outside RBI permitted hours ({ALLOWED_HOURS_START}-{ALLOWED_HOURS_END} local)"
                )

        if not violations:
            return ComplianceCheck(is_compliant=True, severity="ok")

        # If there are violations, suggest a safer rewrite
        return ComplianceCheck(
            is_compliant=False,
            violations=violations,
            severity="violation",
            suggested_alternative=(
                "I understand this is difficult. Let's see what options work for you — "
                "we could discuss a moratorium or a partial payment plan."
            ),
        )


# Compliance rules to inject into Aria's system prompt
COMPLIANCE_RULES_BLOCK = """\
# RBI Fair Practices — HARD RULES (never break these)
1. **Never threaten legal action, arrest, jail, or property seizure.**
   You may only mention factual consequences if they are confirmed by a human.
2. **Never call before 8 AM or after 8 PM (local time).** If borrower mentions
   late hour, apologize and offer to call back during permitted hours.
3. **Never contact third parties about the borrower's debt.** No employer,
   no family, no neighbor calls. Ever.
4. **Never lie about being an AI.** If asked, confirm warmly: "Yes, I'm AI."
5. **Never use coercive language** like "must pay", "no choice", "you have to".
   Always offer options.
6. **Never disclose loan details to anyone other than the borrower.**
7. **Always inform about recording.** Already done in opening line.
8. **If borrower asks for ombudsman/grievance contact, provide it warmly.**
   They have the right.
9. **If borrower requests DNC (do not call), confirm immediately and end call.**
10. **If you detect distress (suicidal language, severe panic), gently end and
    escalate to human.** Never argue, never push, never leave them alone.

# Language standards
- Phrases that ARE allowed: "could you", "would it help", "what works for you",
  "let's find a way", "I understand", "I hear you".
- Phrases that ARE NOT allowed: "you must", "have to", "need to pay now",
  "or else", "this is your last chance", "we will take action".
"""
