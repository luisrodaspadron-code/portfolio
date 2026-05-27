"""V8 LLM review output schema.

The LLM is restricted to narrative critique. It must not return canonical action,
target weight, trim shares, add plan, eligibility, or priority. Any disagreement
with the deterministic engine is recorded as a structured conflict and never
merged into canonical decision fields.
"""

from __future__ import annotations

from typing import Any


LLM_REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "headline",
        "executiveSummary",
        "userExplanation",
        "keyRisks",
        "whyNow",
        "whyNotAlternatives",
        "dataLimitations",
        "followUpQuestions",
        "confidenceNarrative",
        "deterministicDecisionConfirmed",
        "conflictWithDeterministicEngine",
        "advisoryOnlyDisclosure",
    ],
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string"},
        "executiveSummary": {"type": "string"},
        "userExplanation": {"type": "string"},
        "keyRisks": {"type": "array", "items": {"type": "string"}},
        "whyNow": {"type": "array", "items": {"type": "string"}},
        "whyNotAlternatives": {"type": "array", "items": {"type": "string"}},
        "dataLimitations": {"type": "array", "items": {"type": "string"}},
        "followUpQuestions": {"type": "array", "items": {"type": "string"}},
        "confidenceNarrative": {"type": "string"},
        "deterministicDecisionConfirmed": {"type": "boolean"},
        "conflictWithDeterministicEngine": {"type": ["string", "null"]},
        "advisoryOnlyDisclosure": {"type": "string"},
    },
}


FORBIDDEN_LLM_CLAIMS = (
    "guaranteed",
    "guarantee",
    "will outperform",
    "best predictor",
    "risk-free",
    "no risk",
    "execute trade",
    "order placed",
    "filled at",
    "ai decided",
)


def detect_forbidden_claims(text: str) -> list[str]:
    """Return forbidden phrases present in the LLM narrative (lower-cased match)."""

    if not text:
        return []
    lowered = text.lower()
    return [phrase for phrase in FORBIDDEN_LLM_CLAIMS if phrase in lowered]


def detect_decision_conflict(
    review_output: dict[str, Any],
    deterministic_first_action_symbol: str | None,
    deterministic_first_action_label: str | None,
) -> str | None:
    """Return a short conflict message if the LLM output disagrees with deterministic state.

    The deterministic engine owns action labels. If the LLM says
    ``deterministicDecisionConfirmed: false`` or its narrative explicitly contradicts
    the deterministic first action symbol/label, the conflict is recorded.
    """

    confirmed = bool(review_output.get("deterministicDecisionConfirmed", True))
    explicit_conflict = (review_output.get("conflictWithDeterministicEngine") or "").strip()
    if explicit_conflict:
        return explicit_conflict
    if not confirmed and deterministic_first_action_symbol:
        return (
            f"LLM did not confirm deterministic first action for {deterministic_first_action_symbol} "
            f"({deterministic_first_action_label or 'unknown action'})."
        )
    return None
