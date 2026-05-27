from __future__ import annotations

from typing import Any

PROMPT_VERSION = "llm-review.v1"


def build_llm_review_packet(
    packet: dict[str, Any],
    deterministic: dict[str, Any],
    *,
    run_id: str = "",
    specialist_summaries: dict[str, Any] | None = None,
) -> dict[str, Any]:
    real = packet.get("portfolio", {}).get("real") or {}
    holdings = real.get("positions") or []
    top_exposures = sorted(holdings, key=lambda item: float(item.get("weight") or 0), reverse=True)[:8]
    hard_breaches = list(packet.get("risk_breaches") or [])[:12]
    holding_items = deterministic.get("holding_decisions") or []
    opportunity_items = deterministic.get("opportunity_decisions") or []
    eligible = [item for item in opportunity_items if item.get("decision") in {"Add", "Stagger Entry"} and item.get("eligibility") != "fail"]
    ineligible = [item for item in opportunity_items if item.get("decision") in {"Avoid", "Wait For Data"} or item.get("eligibility") == "fail"]
    urgent_trims = [item for item in holding_items if item.get("decision") == "Trim"]
    first_action = urgent_trims[0] if urgent_trims else (eligible[0] if eligible else (holding_items[0] if holding_items else None))
    blocked: list[str] = []
    if urgent_trims:
        blocked.append("New single-stock adds are blocked until hard concentration breaches are remediated.")
    sector_breaches = [item for item in hard_breaches if "sector" in str(item).lower()]
    if sector_breaches:
        blocked.append("Adds in overweight sectors are blocked until sector exposure is reduced.")

    return {
        "promptVersion": PROMPT_VERSION,
        "runId": run_id or packet.get("packet_hash", ""),
        "portfolioValue": float(real.get("total_value") or 0),
        "cashValue": float(real.get("cash") or 0),
        "topExposures": [
            {
                "symbol": item.get("symbol"),
                "weight": round(float(item.get("weight") or 0), 4),
                "sector": item.get("sector"),
                "value": round(float(item.get("market_value") or 0), 2),
            }
            for item in top_exposures
        ],
        "hardBreaches": hard_breaches,
        "blockedActions": blocked,
        "eligibleCandidates": [
            {
                "symbol": item.get("symbol"),
                "decision": item.get("decision"),
                "targetWeight": item.get("target_weight"),
                "score": item.get("confidence_score"),
                "reasonCode": item.get("reason_code"),
            }
            for item in eligible[:6]
        ],
        "ineligibleCandidates": [
            {
                "symbol": item.get("symbol"),
                "decision": item.get("decision"),
                "reasonCode": item.get("reason_code"),
                "blockers": (item.get("detail_payload") or {}).get("blockers") or [],
            }
            for item in ineligible[:6]
        ],
        "dataQualitySummary": packet.get("data_quality") or {},
        "macroRegimeSummary": str((packet.get("macro_regime") or {}).get("label") or "unknown"),
        "factorSummary": "Deterministic factor scores are attached to each candidate; do not invent factor values.",
        "deterministicFirstAction": {
            "symbol": first_action.get("symbol") if first_action else None,
            "decision": first_action.get("decision") if first_action else None,
            "reasonCode": first_action.get("reason_code") if first_action else None,
            "targetWeight": first_action.get("target_weight") if first_action else None,
        },
        "deterministicVerdict": deterministic.get("portfolio_verdict"),
        "specialistSummaries": specialist_summaries or {},
        "forbiddenToAlter": [
            "trimPlan",
            "addPlan",
            "target_weight for hard risk breaches",
            "eligibility for failed risk gates",
            "portfolio weights and share counts",
        ],
        "questionsForLLM": [
            "Does the deterministic first action make sense given the breaches and data quality?",
            "What alternatives were considered and why were they deprioritized?",
            "What data limitations should the user understand before acting?",
        ],
    }
