from __future__ import annotations

from typing import Any

from app.services.candidate_scoring import score_candidate
from app.services.policy_engine import RiskPolicy, selected_risk_policy


def evaluate_candidate(
    candidate: dict[str, Any],
    target_weight: float,
    rules: dict[str, Any],
    *,
    current_sector_weight: float = 0.0,
    policy: RiskPolicy | None = None,
) -> tuple[str, list[str]]:
    """Evaluate a candidate using V8 policy rules.

    The ``rules`` dict is the legacy guardrails (still consulted for liquidity
    floors); the canonical ``policy`` argument is preferred when callers have it.
    Returns ``(status, flags)`` where status is ``pass`` / ``watch`` / ``fail``.
    """

    flags: list[str] = []
    asset_class = candidate.get("asset_class")
    sector = candidate.get("sector", "Unknown")
    symbol = candidate.get("symbol", "")
    liquidity = candidate.get("liquidity_score", 0)
    risk_score = candidate.get("risk_score", 1.0)
    sector_cap = float(rules.get("max_sector_weight") or (policy.sector.hard_cap if policy else 0.30))

    if liquidity < rules.get("min_liquidity_score", 65):
        flags.append(f"{symbol} liquidity score is below the configured floor.")
    if asset_class == "Stock" and target_weight > rules.get("max_single_stock_weight", 0.15):
        flags.append(f"{symbol} would exceed the single-stock cap.")
    if asset_class == "ETF" and target_weight > rules.get("max_etf_weight", 0.60):
        flags.append(f"{symbol} would exceed the ETF cap.")
    if "Crypto" in sector and target_weight > rules.get("max_crypto_weight", 0.03):
        flags.append(f"{symbol} would exceed the crypto/direct commodity cap.")
    if risk_score > 0.42:
        flags.append(f"{symbol} has elevated standalone volatility/drawdown risk.")
    if current_sector_weight >= sector_cap:
        flags.append(f"New adds in {sector} are blocked while sector exposure is at or above the {sector_cap:.0%} cap.")
    elif current_sector_weight + target_weight > sector_cap:
        flags.append(f"{symbol} would push {sector} above the {sector_cap:.0%} sector cap.")

    if policy is not None:
        score = score_candidate(candidate, policy, current_sector_weight=current_sector_weight)
        for blocker in score.blockers:
            if blocker not in flags:
                flags.append(blocker)

    status = "pass" if not flags else "watch"
    if liquidity < rules.get("min_liquidity_score", 65) * 0.75 or risk_score > 0.68:
        status = "fail"
    if any("sector" in flag.lower() and "blocked" in flag.lower() for flag in flags):
        status = "fail"
    elif any("sector cap" in flag.lower() for flag in flags):
        status = "fail"
    if policy is not None and any(score_blocker in flags for score_blocker in []):
        status = "fail"
    return status, flags


def target_weight_for_candidate(candidate: dict[str, Any], rules: dict[str, Any]) -> float:
    score = max(candidate.get("score", 0), 0)
    base = min(0.02 + score * 0.22 + candidate.get("confidence", 0.4) * 0.05, 0.16)
    if candidate.get("asset_class") == "ETF":
        cap = rules.get("max_etf_weight", 0.60)
    else:
        cap = rules.get("max_single_stock_weight", 0.15)
    if "Crypto" in candidate.get("sector", ""):
        cap = min(cap, rules.get("max_crypto_weight", 0.03))
    return round(max(0.01, min(base, cap)), 4)
