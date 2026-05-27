from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import floor
from typing import Any, Literal


Freshness = Literal["live", "recent", "stale", "missing"]
Coverage = Literal["complete", "partial", "insufficient", "missing"]
TrimMode = Literal["redeploy_or_cash", "withdrawal"]


DEFAULT_RISK_POLICY = {
    "maxSingleStockWeight": 0.08,
    "maxSectorWeight": 0.30,
    "maxCryptoWeight": 0.10,
    "maxSingleCryptoWeight": 0.03,
    "maxIlliquidPositionWeight": 0.03,
    "maxNewPositionWeight": 0.03,
    "minPriceFreshnessSecondsEquityLive": 900,
    "minPriceFreshnessSecondsEquityRecent": 86_400,
    "minPriceFreshnessSecondsCryptoLive": 300,
    "minHistoryDaysForFullSignal": 252,
    "minHistoryDaysForRestrictedSignal": 63,
    "minDollarVolume": 5_000_000,
    "maxStandaloneDrawdownForAdd": 0.25,
    "maxAnnualizedVolForAdd": 0.60,
    "targetTranchesDefault": 4,
    "targetTranchesMin": 3,
    "targetTranchesMax": 5,
}


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
    currentValue: float
    targetValue: float
    estimatedSellValue: float
    estimatedExecutedSellValue: float
    sharesToSellExact: float
    sharesToSell: float
    sharesToSellWhole: int
    estimatedPostWeight: float
    priceUsed: float
    priceTimestamp: str
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


def data_quality_from_price(
    *,
    provider: str,
    source_timestamp: str = "",
    received_at: str | None = None,
    asset_class: str = "stock",
    coverage: Coverage = "complete",
    sample: bool = False,
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


def cap_distance(current_weight: float, limit: float) -> dict[str, float | bool]:
    over_by = round(max(0.0, current_weight - limit), 4)
    return {
        "current_weight": round(current_weight, 4),
        "limit": round(limit, 4),
        "over_by": over_by,
        "breached": over_by > 0,
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
) -> dict[str, Any]:
    if total_portfolio_value <= 0:
        raise ValueError("Total portfolio value must be positive.")
    if live_price <= 0:
        raise ValueError("A positive live/reference price is required for trim sizing.")
    if not 0 <= target_weight < 1:
        raise ValueError("Target weight must be between 0 and 1.")

    target_value = total_portfolio_value * target_weight
    if mode == "withdrawal":
        sell_value = max(0.0, (current_position_value - target_weight * total_portfolio_value) / (1 - target_weight))
    else:
        sell_value = max(0.0, current_position_value - target_value)
    shares_exact = min(max(quantity, 0.0), sell_value / live_price)
    shares_whole = floor(shares_exact)
    shares_to_sell = round_down(shares_exact, 4) if fractional_shares else float(shares_whole)
    executed_sell_value = shares_to_sell * live_price
    post_position_value = max(0.0, current_position_value - executed_sell_value)
    post_total_value = total_portfolio_value - executed_sell_value if mode == "withdrawal" else total_portfolio_value
    post_weight = post_position_value / post_total_value if post_total_value else 0.0
    tax_warning = ""
    if avg_cost > 0:
        tax_warning = "Average cost is available; review realized gain/loss and tax impact before acting."
    return TrimPlan(
        mode=mode,
        currentValue=round(current_position_value, 2),
        targetValue=round(target_value, 2),
        estimatedSellValue=round(sell_value, 2),
        estimatedExecutedSellValue=round(executed_sell_value, 2),
        sharesToSellExact=round(shares_exact, 6),
        sharesToSell=round(shares_to_sell, 4),
        sharesToSellWhole=shares_whole,
        estimatedPostWeight=round(post_weight, 4),
        priceUsed=round(live_price, 4),
        priceTimestamp=price_timestamp,
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

