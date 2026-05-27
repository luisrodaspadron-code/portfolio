from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import ceil, floor
from typing import Any, Literal


Freshness = Literal["live", "recent", "stale", "partial", "missing"]
Coverage = Literal["complete", "partial", "insufficient", "missing"]
TrimMode = Literal["redeploy_or_cash", "withdrawal"]
TrimComplianceMode = Literal["strict_below_threshold", "reduce_only", "tax_aware_review"]


from app.services.policy_engine import (
    RiskPolicy,
    SingleStockPolicy,
    build_cap_distance as _policy_cap_distance,
    policy_state_for_weight,
)
from app.services.risk_policy import DEFAULT_RISK_POLICY


@dataclass(frozen=True)
class DataQuality:
    provider: str
    sourceTimestamp: str
    receivedAt: str
    ageSeconds: int
    freshness: Freshness
    coverage: Coverage
    confidence: float
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrimPlan:
    mode: TrimMode
    complianceMode: TrimComplianceMode
    currentValue: float
    targetValue: float
    estimatedSellValue: float
    estimatedExecutedSellValue: float
    sharesToSellExact: float
    sharesToSell: float
    sharesToSellWhole: int
    sharesToSellWholeCompliant: int
    sharesToSellWholeReduceOnly: int
    sharesToSellFractionalCompliant: float
    estimatedPostWeight: float
    estimatedPostWeightCompliant: float
    estimatedPostWeightReduceOnly: float
    wouldRemainAboveThresholdIfRoundedDown: bool
    policyThreshold: float
    priceUsed: float
    priceTimestamp: str
    executionGuidance: dict[str, Any]
    advisoryOnly: bool = True
    taxWarning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AddPlan:
    targetWeight: float
    initialWeight: float
    trancheCount: int
    trancheSchedule: list[dict[str, Any]]
    sectorImpact: float
    riskBudgetImpact: float
    blockers: list[str]
    advisoryOnly: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{normalized}T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def round_down(value: float, decimals: int = 4) -> float:
    factor = 10**decimals
    return floor(max(value, 0) * factor) / factor


def round_up(value: float, decimals: int = 4) -> float:
    factor = 10**decimals
    return ceil(max(value, 0) * factor) / factor


def data_quality_from_price(
    *,
    provider: str,
    source_timestamp: str = "",
    received_at: str | None = None,
    asset_class: str = "stock",
    coverage: Coverage = "complete",
    sample: bool = False,
    policy: RiskPolicy | None = None,
) -> dict[str, Any]:
    received = _parse_timestamp(received_at or _now()) or datetime.now(timezone.utc)
    source = _parse_timestamp(source_timestamp)
    warnings: list[str] = []
    if not source:
        return DataQuality(
            provider=provider or "missing",
            sourceTimestamp="",
            receivedAt=received.isoformat(),
            ageSeconds=999_999_999,
            freshness="missing",
            coverage="missing",
            confidence=0.0,
            warnings=["No usable price timestamp is available."],
        ).to_dict()
    age = max(0, int((received - source).total_seconds()))
    if policy is not None:
        live_limit = policy.data_quality.crypto_live_seconds if asset_class.lower() == "crypto" else policy.data_quality.equity_live_seconds
        recent_limit = policy.data_quality.equity_recent_seconds
    else:
        live_limit = DEFAULT_RISK_POLICY["minPriceFreshnessSecondsCryptoLive"] if asset_class.lower() == "crypto" else DEFAULT_RISK_POLICY["minPriceFreshnessSecondsEquityLive"]
        recent_limit = DEFAULT_RISK_POLICY["minPriceFreshnessSecondsEquityRecent"]
    if sample:
        freshness: Freshness = "stale"
        confidence = 0.35
        warnings.append("Sample data lowers confidence and cannot be treated as live.")
    elif age <= live_limit:
        freshness = "live"
        confidence = 1.0
    elif age <= recent_limit:
        freshness = "recent"
        confidence = 0.82
    else:
        freshness = "stale"
        confidence = 0.45
        warnings.append("Price data is older than the freshness policy.")
    if coverage != "complete":
        confidence = min(confidence, 0.62)
        warnings.append(f"Coverage is {coverage}.")
    return DataQuality(
        provider=provider or "unknown",
        sourceTimestamp=source.isoformat(),
        receivedAt=received.isoformat(),
        ageSeconds=age,
        freshness=freshness,
        coverage=coverage,
        confidence=round(confidence, 4),
        warnings=warnings,
    ).to_dict()


def cap_distance(
    current_weight: float,
    limit: float | None = None,
    *,
    single_stock: SingleStockPolicy | None = None,
) -> dict[str, Any]:
    """Return cap-distance for a single position.

    Backwards-compatible behavior: when ``limit`` is provided (legacy callers), the
    returned dict still includes ``current_weight``, ``limit``, ``over_by`` and
    ``breached`` fields. When ``single_stock`` is provided (V8 callers), the returned
    dict additionally includes the multi-threshold ladder (``target``, ``warning``,
    ``hardBuyBlock``, ``urgentReview``, ``extreme``), per-threshold overage, and
    ``state``/``blocksNewBuys``/``requiresTrimPlan``.
    """

    payload: dict[str, Any]
    if single_stock is not None:
        payload = _policy_cap_distance(current_weight, single_stock)
        legacy_limit = float(limit) if limit is not None else float(single_stock.urgent_review)
        legacy_over = round(max(0.0, current_weight - legacy_limit), 4)
        payload.update(
            {
                "current_weight": round(current_weight, 4),
                "limit": round(legacy_limit, 4),
                "over_by": legacy_over,
                "breached": legacy_over > 0,
            }
        )
        return payload

    if limit is None:
        raise ValueError("cap_distance requires either a single_stock policy or a legacy limit.")

    legacy_limit = float(limit)
    legacy_over = round(max(0.0, current_weight - legacy_limit), 4)
    return {
        "current_weight": round(current_weight, 4),
        "limit": round(legacy_limit, 4),
        "over_by": legacy_over,
        "breached": legacy_over > 0,
    }


def build_trim_plan(
    *,
    total_portfolio_value: float,
    current_position_value: float,
    target_weight: float,
    live_price: float,
    price_timestamp: str,
    quantity: float,
    avg_cost: float = 0.0,
    fractional_shares: bool = True,
    mode: TrimMode = "redeploy_or_cash",
    compliance_mode: TrimComplianceMode = "strict_below_threshold",
    fractional_precision: int = 4,
    policy_threshold: float | None = None,
) -> dict[str, Any]:
    """Build a trim plan with explicit compliance math.

    V8 compliance modes:
      * ``strict_below_threshold`` — whole-share rounding uses ``ceil``; fractional
        rounding uses ``round_up_to_precision``. Guarantees post-trim weight is
        strictly below the policy threshold.
      * ``reduce_only`` — whole-share rounding uses ``floor``. May leave the
        position above the policy threshold and must be labeled as such.
      * ``tax_aware_review`` — same math as ``reduce_only`` plus a mandatory tax
        warning when ``avg_cost > 0``.
    """

    if total_portfolio_value <= 0:
        raise ValueError("Total portfolio value must be positive.")
    if live_price <= 0:
        raise ValueError("A positive live/reference price is required for trim sizing.")
    if not 0 <= target_weight < 1:
        raise ValueError("Target weight must be between 0 and 1.")

    threshold = float(policy_threshold) if policy_threshold is not None else float(target_weight)
    if threshold < 0:
        threshold = 0.0
    target_value = total_portfolio_value * target_weight
    if mode == "withdrawal":
        sell_value = max(0.0, (current_position_value - target_weight * total_portfolio_value) / (1 - target_weight))
    else:
        sell_value = max(0.0, current_position_value - target_value)
    shares_exact_raw = sell_value / live_price
    shares_exact = min(max(quantity, 0.0), shares_exact_raw)
    shares_whole_floor = max(0, min(int(floor(shares_exact)), int(floor(quantity))))
    shares_whole_ceil_raw = ceil(shares_exact)
    shares_whole_ceil = max(0, min(int(shares_whole_ceil_raw), int(floor(quantity))))
    shares_fractional_strict = min(round_up(shares_exact, fractional_precision), round_down(quantity, fractional_precision))
    shares_fractional_reduce = round_down(shares_exact, fractional_precision)

    if compliance_mode == "strict_below_threshold":
        whole_shares_chosen = shares_whole_ceil
        fractional_shares_chosen = shares_fractional_strict
    else:
        whole_shares_chosen = shares_whole_floor
        fractional_shares_chosen = shares_fractional_reduce

    shares_to_sell = fractional_shares_chosen if fractional_shares else float(whole_shares_chosen)
    executed_sell_value = shares_to_sell * live_price
    post_position_value = max(0.0, current_position_value - executed_sell_value)
    post_total_value = total_portfolio_value - executed_sell_value if mode == "withdrawal" else total_portfolio_value
    post_weight = post_position_value / post_total_value if post_total_value else 0.0

    executed_reduce_only_value = float(shares_whole_floor) * live_price if not fractional_shares else shares_fractional_reduce * live_price
    post_reduce_value = max(0.0, current_position_value - executed_reduce_only_value)
    post_reduce_total = total_portfolio_value - executed_reduce_only_value if mode == "withdrawal" else total_portfolio_value
    post_weight_reduce_only = post_reduce_value / post_reduce_total if post_reduce_total else 0.0

    executed_compliant_value = float(shares_whole_ceil) * live_price if not fractional_shares else shares_fractional_strict * live_price
    post_compliant_value = max(0.0, current_position_value - executed_compliant_value)
    post_compliant_total = total_portfolio_value - executed_compliant_value if mode == "withdrawal" else total_portfolio_value
    post_weight_compliant = post_compliant_value / post_compliant_total if post_compliant_total else 0.0

    would_remain_above = post_weight_reduce_only > threshold + 1e-9

    tax_warning = ""
    if avg_cost > 0:
        if compliance_mode == "tax_aware_review":
            tax_warning = (
                "Average cost is available; this trim mode is reduce-only and may leave the position above policy. "
                "Review realized gain/loss and tax impact before acting."
            )
        else:
            tax_warning = "Average cost is available; review realized gain/loss and tax impact before acting."

    guidance_shares = float(shares_whole_ceil if not fractional_shares else shares_fractional_strict)
    guidance_value = guidance_shares * live_price
    should_stage = guidance_value >= 10_000 or guidance_shares >= 25 or current_position_value / total_portfolio_value >= 0.25
    slice_count = 1 if not should_stage else max(2, min(4, ceil(guidance_value / 10_000)))
    limit_price = round(live_price * 0.995, 2)
    stop_review_price = round(live_price * 0.98, 2)

    def _split_integer_shares(total: int, count: int) -> list[int]:
        base = total // count
        remainder = total % count
        return [base + (1 if index < remainder else 0) for index in range(count)]

    def _slice_payload(index: int, shares: float) -> dict[str, Any]:
        return {
            "sliceNumber": index,
            "shares": shares,
            "estimatedValue": round(shares * live_price, 2),
            "suggestedLimitPrice": limit_price,
            "timeInForce": "day",
            "condition": "Only after confirming a current bid/ask and portfolio value in the broker.",
        }

    fractional_slices: list[dict[str, Any]] = []
    whole_share_slices: list[dict[str, Any]] = []
    if fractional_shares:
        per_slice = guidance_shares / slice_count if slice_count else 0
        allocated = 0.0
        for index in range(1, slice_count + 1):
            shares = round(per_slice, fractional_precision) if index < slice_count else round(max(0.0, guidance_shares - allocated), fractional_precision)
            allocated += shares
            fractional_slices.append(_slice_payload(index, shares))
    for index, shares in enumerate(_split_integer_shares(int(shares_whole_ceil), slice_count), start=1):
        whole_share_slices.append(_slice_payload(index, shares))
    slices = fractional_slices if fractional_shares else whole_share_slices

    execution_guidance = {
        "advisoryOnly": True,
        "brokerActionLabel": "Create limit sell checklist",
        "preferredOrderType": "limit_sell",
        "timeInForce": "day",
        "session": "regular_market_hours",
        "recommendedStyle": "staged_limit_sells" if should_stage else "single_limit_sell",
        "sliceCount": slice_count,
        "limitPriceReference": round(live_price, 4),
        "suggestedLimitPrice": limit_price,
        "stopReviewBelow": stop_review_price,
        "priceRefreshRequired": True,
        "primaryQuantityBasis": "fractional" if fractional_shares else "whole_share_compliant",
        "slices": slices,
        "wholeShareSlices": whole_share_slices,
        "fractionalSlices": fractional_slices,
        "singleOrderAlternative": {
            "shares": round(guidance_shares, fractional_precision) if fractional_shares else int(shares_whole_ceil),
            "estimatedValue": round(guidance_value, 2),
            "suggestedLimitPrice": limit_price,
            "timeInForce": "day",
        },
        "allAtOnceAcceptable": not should_stage,
        "stagingRationale": (
            "Staged limit sells are suggested because the trim is large relative to the portfolio or share count."
            if should_stage
            else "A single limit sell checklist is reasonable for this trim size after refreshing the quote."
        ),
        "instructions": [
            "Refresh the live quote and bid/ask spread in the broker before using this checklist.",
            "Use a limit sell checklist rather than a market sell when the reference price is stale or spread visibility is missing.",
            "If using whole shares, the compliant quantity is the amount that clears the selected policy threshold in one review.",
            "If the live price moves materially before entry, rerun the advisor instead of reusing this ticket.",
        ],
        "invalidation": [
            "Live/reference price is below the stop-review price.",
            "Provider freshness is stale or missing after refresh.",
            "Position quantity, portfolio value, or policy preset changed.",
            "Tax review changes the acceptable trim amount.",
        ],
    }

    return TrimPlan(
        mode=mode,
        complianceMode=compliance_mode,
        currentValue=round(current_position_value, 2),
        targetValue=round(target_value, 2),
        estimatedSellValue=round(sell_value, 2),
        estimatedExecutedSellValue=round(executed_sell_value, 2),
        sharesToSellExact=round(shares_exact, 6),
        sharesToSell=round(shares_to_sell, 4),
        sharesToSellWhole=int(whole_shares_chosen),
        sharesToSellWholeCompliant=int(shares_whole_ceil),
        sharesToSellWholeReduceOnly=int(shares_whole_floor),
        sharesToSellFractionalCompliant=round(shares_fractional_strict, fractional_precision),
        estimatedPostWeight=round(post_weight, 4),
        estimatedPostWeightCompliant=round(post_weight_compliant, 4),
        estimatedPostWeightReduceOnly=round(post_weight_reduce_only, 4),
        wouldRemainAboveThresholdIfRoundedDown=bool(would_remain_above),
        policyThreshold=round(threshold, 4),
        priceUsed=round(live_price, 4),
        priceTimestamp=price_timestamp,
        executionGuidance=execution_guidance,
        advisoryOnly=True,
        taxWarning=tax_warning,
    ).to_dict()


def build_add_plan(
    *,
    total_portfolio_value: float,
    target_weight: float,
    current_sector_weight: float,
    sector_cap: float,
    blockers: list[str] | None = None,
    tranche_count: int | None = None,
) -> dict[str, Any]:
    count = tranche_count or DEFAULT_RISK_POLICY["targetTranchesDefault"]
    count = max(DEFAULT_RISK_POLICY["targetTranchesMin"], min(DEFAULT_RISK_POLICY["targetTranchesMax"], count))
    target_weight = max(0.0, target_weight)
    blockers = list(blockers or [])
    if current_sector_weight + target_weight > sector_cap:
        blockers.append("Sector cap would be breached by this add.")
    initial_weight = min(target_weight / count, DEFAULT_RISK_POLICY["maxNewPositionWeight"])
    schedule = []
    for index in range(1, count + 1):
        weight = round(min(target_weight, initial_weight * index), 4)
        schedule.append(
            {
                "trancheNumber": index,
                "targetDateOrCondition": "Next review window" if index == 1 else f"After review {index}",
                "estimatedWeight": weight,
                "estimatedDollarAmount": round(total_portfolio_value * weight, 2),
                "trigger": "Fresh data still passes liquidity, volatility, drawdown, and risk gates.",
                "invalidation": "Stop if data turns stale, the score falls below portfolio alternatives, or a hard cap would be breached.",
            }
        )
    return AddPlan(
        targetWeight=round(target_weight, 4),
        initialWeight=round(initial_weight, 4),
        trancheCount=count,
        trancheSchedule=schedule,
        sectorImpact=round(current_sector_weight + target_weight, 4),
        riskBudgetImpact=round(target_weight, 4),
        blockers=blockers,
        advisoryOnly=True,
    ).to_dict()
