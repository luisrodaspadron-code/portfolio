"""Canonical risk-policy engine for Signal Prime.

V8 multi-threshold policy. A single magic 8% cap is not acceptable; every position
threshold is a five-level ladder (target, warning, hardBuyBlock, urgentReview, extreme).

The dataclasses are immutable. Use `selected_risk_policy(conn)` to read the policy
in service code, and `risk_policy_to_dict()` to expose it to the wire/UI.

Legacy guardrail fields (``max_single_stock_weight`` and friends) are emitted by
``legacy_rules_from_policy()`` for back-compat with code paths that have not been
migrated yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal


POLICY_VERSION = "risk-policy.v2"

PolicyState = Literal["ok", "warning", "hard_buy_block", "urgent_review", "extreme"]
PolicyPreset = Literal["conservative", "balanced", "aggressive", "competition", "custom"]
TrimComplianceMode = Literal["strict_below_threshold", "reduce_only", "tax_aware_review"]


@dataclass(frozen=True)
class SingleStockPolicy:
    target: float
    warning: float
    hard_buy_block: float
    urgent_review: float
    extreme: float


@dataclass(frozen=True)
class SectorPolicy:
    warning: float
    hard_cap: float
    use_benchmark_relative_cap: bool = False
    max_active_overweight: float = 0.10


@dataclass(frozen=True)
class BroadEtfPolicy:
    exempt_from_single_stock_cap: bool = True
    use_look_through_when_available: bool = True
    max_single_broad_etf: float = 0.60


@dataclass(frozen=True)
class ThematicEtfPolicy:
    max_single_thematic_etf: float = 0.15
    require_look_through_or_theme_risk_label: bool = True


@dataclass(frozen=True)
class SingleNewStockAddPolicy:
    initial_max: float = 0.03
    target_max: float = 0.05
    block_if_worsens_existing_breach: bool = True
    allow_if_risk_reducing_with_new_cash: bool = True


@dataclass(frozen=True)
class CryptoPolicy:
    enabled_by_default: bool = False
    max_total: float = 0.03
    max_single: float = 0.03
    require_explicit_user_enablement: bool = True
    require_24x7_freshness: bool = True
    require_custody_warning: bool = True


@dataclass(frozen=True)
class DataQualityPolicy:
    equity_live_seconds: int = 900
    equity_recent_seconds: int = 86_400
    crypto_live_seconds: int = 300
    crypto_recent_seconds: int = 1_800
    min_history_days_restricted: int = 63
    min_history_days_full: int = 252
    min_history_days_watch_only: int = 20


@dataclass(frozen=True)
class LiquidityPolicy:
    min_dollar_volume_default: float = 5_000_000
    max_trade_percent_of_adv: float = 0.01


@dataclass(frozen=True)
class RemediationPolicy:
    allow_risk_reducing_trades_during_breach: bool = True
    block_risk_increasing_trades_during_breach: bool = True
    require_tax_warning_for_taxable_accounts: bool = True
    default_tranches: int = 4
    min_tranches: int = 3
    max_tranches: int = 5


@dataclass(frozen=True)
class RiskPolicy:
    id: str
    name: str
    preset: PolicyPreset
    advisory_only: bool
    single_stock: SingleStockPolicy
    sector: SectorPolicy
    broad_etf: BroadEtfPolicy
    thematic_etf: ThematicEtfPolicy
    single_new_stock_add: SingleNewStockAddPolicy
    crypto: CryptoPolicy
    data_quality: DataQualityPolicy
    liquidity: LiquidityPolicy
    remediation: RemediationPolicy
    version: str = POLICY_VERSION


CONSERVATIVE = RiskPolicy(
    id="conservative",
    name="Conservative",
    preset="conservative",
    advisory_only=True,
    single_stock=SingleStockPolicy(
        target=0.03, warning=0.05, hard_buy_block=0.06, urgent_review=0.10, extreme=0.18
    ),
    sector=SectorPolicy(warning=0.18, hard_cap=0.22, max_active_overweight=0.08),
    broad_etf=BroadEtfPolicy(max_single_broad_etf=0.55),
    thematic_etf=ThematicEtfPolicy(max_single_thematic_etf=0.08),
    single_new_stock_add=SingleNewStockAddPolicy(initial_max=0.02, target_max=0.03),
    crypto=CryptoPolicy(max_total=0.01, max_single=0.01),
    data_quality=DataQualityPolicy(),
    liquidity=LiquidityPolicy(min_dollar_volume_default=10_000_000),
    remediation=RemediationPolicy(default_tranches=4),
)


BALANCED = RiskPolicy(
    id="balanced",
    name="Balanced",
    preset="balanced",
    advisory_only=True,
    single_stock=SingleStockPolicy(
        target=0.05, warning=0.08, hard_buy_block=0.10, urgent_review=0.15, extreme=0.25
    ),
    sector=SectorPolicy(warning=0.25, hard_cap=0.30),
    broad_etf=BroadEtfPolicy(),
    thematic_etf=ThematicEtfPolicy(),
    single_new_stock_add=SingleNewStockAddPolicy(),
    crypto=CryptoPolicy(),
    data_quality=DataQualityPolicy(),
    liquidity=LiquidityPolicy(),
    remediation=RemediationPolicy(),
)


AGGRESSIVE = RiskPolicy(
    id="aggressive",
    name="Aggressive",
    preset="aggressive",
    advisory_only=True,
    single_stock=SingleStockPolicy(
        target=0.08, warning=0.12, hard_buy_block=0.15, urgent_review=0.20, extreme=0.30
    ),
    sector=SectorPolicy(warning=0.30, hard_cap=0.40),
    broad_etf=BroadEtfPolicy(),
    thematic_etf=ThematicEtfPolicy(max_single_thematic_etf=0.20),
    single_new_stock_add=SingleNewStockAddPolicy(initial_max=0.05, target_max=0.08),
    crypto=CryptoPolicy(max_total=0.05, max_single=0.03),
    data_quality=DataQualityPolicy(),
    liquidity=LiquidityPolicy(),
    remediation=RemediationPolicy(default_tranches=3),
)


COMPETITION = RiskPolicy(
    id="competition",
    name="Competition",
    preset="competition",
    advisory_only=True,
    single_stock=SingleStockPolicy(
        target=0.10, warning=0.15, hard_buy_block=0.18, urgent_review=0.25, extreme=0.35
    ),
    sector=SectorPolicy(warning=0.35, hard_cap=0.45),
    broad_etf=BroadEtfPolicy(),
    thematic_etf=ThematicEtfPolicy(max_single_thematic_etf=0.25),
    single_new_stock_add=SingleNewStockAddPolicy(initial_max=0.06, target_max=0.10),
    crypto=CryptoPolicy(max_total=0.08, max_single=0.05),
    data_quality=DataQualityPolicy(),
    liquidity=LiquidityPolicy(),
    remediation=RemediationPolicy(default_tranches=3, min_tranches=2),
)


PRESETS: dict[str, RiskPolicy] = {
    "conservative": CONSERVATIVE,
    "balanced": BALANCED,
    "aggressive": AGGRESSIVE,
    "competition": COMPETITION,
}

PRESET_DISPLAY: dict[str, dict[str, str]] = {
    "conservative": {
        "label": "Conservative",
        "description": "Tight single-name caps, defensive sector caps, crypto effectively off. Lower urgency adds.",
    },
    "balanced": {
        "label": "Balanced",
        "description": "5% single-name targets, 8% warning, 10% hard buy-block, 15% urgent review, 25% extreme. Default for most users.",
    },
    "aggressive": {
        "label": "Aggressive",
        "description": "Larger single-name conviction allowed; sector caps relaxed but still enforced. Crypto small but allowed.",
    },
    "competition": {
        "label": "Competition",
        "description": "Highest conviction sizing for competition-grade portfolios. Higher thresholds but still advisory-only.",
    },
}


def get_policy(preset: str) -> RiskPolicy:
    """Return a known preset policy, falling back to balanced when unknown."""

    return PRESETS.get((preset or "").lower(), BALANCED)


def policy_state_for_weight(weight: float, single_stock: SingleStockPolicy) -> PolicyState:
    if weight >= single_stock.extreme:
        return "extreme"
    if weight >= single_stock.urgent_review:
        return "urgent_review"
    if weight >= single_stock.hard_buy_block:
        return "hard_buy_block"
    if weight >= single_stock.warning:
        return "warning"
    return "ok"


def build_cap_distance(current_weight: float, single_stock: SingleStockPolicy) -> dict[str, Any]:
    """Return the V8 multi-threshold cap distance for a single position."""

    state = policy_state_for_weight(current_weight, single_stock)
    return {
        "currentWeight": round(current_weight, 4),
        "target": single_stock.target,
        "warning": single_stock.warning,
        "hardBuyBlock": single_stock.hard_buy_block,
        "urgentReview": single_stock.urgent_review,
        "extreme": single_stock.extreme,
        "overTargetBy": round(max(0.0, current_weight - single_stock.target), 4),
        "overWarningBy": round(max(0.0, current_weight - single_stock.warning), 4),
        "overHardBuyBlockBy": round(max(0.0, current_weight - single_stock.hard_buy_block), 4),
        "overUrgentReviewBy": round(max(0.0, current_weight - single_stock.urgent_review), 4),
        "overExtremeBy": round(max(0.0, current_weight - single_stock.extreme), 4),
        "state": state,
        "blocksNewBuys": state in {"hard_buy_block", "urgent_review", "extreme"},
        "requiresTrimPlan": state in {"urgent_review", "extreme"},
    }


def threshold_for_state(single_stock: SingleStockPolicy, state: PolicyState) -> float:
    if state == "extreme":
        return single_stock.extreme
    if state == "urgent_review":
        return single_stock.urgent_review
    if state == "hard_buy_block":
        return single_stock.hard_buy_block
    if state == "warning":
        return single_stock.warning
    return single_stock.target


def legacy_rules_from_policy(policy: RiskPolicy) -> dict[str, Any]:
    """Project the canonical policy down to the legacy guardrail field names.

    ``max_single_stock_weight`` maps to the level at which the deterministic engine
    must trim (``urgent_review``); ``max_etf_weight`` maps to the broad-ETF single
    ceiling; ``max_sector_weight`` maps to ``sector.hard_cap``. This keeps the older
    decision-service paths working while V8 migration is in flight.
    """

    return {
        "max_single_stock_weight": policy.single_stock.urgent_review,
        "max_etf_weight": policy.broad_etf.max_single_broad_etf,
        "max_sector_weight": policy.sector.hard_cap,
        "max_crypto_weight": policy.crypto.max_total,
        "max_positions": 28 if policy.preset == "conservative" else 18 if policy.preset == "balanced" else 14,
        "min_liquidity_score": 75 if policy.preset == "conservative" else 70 if policy.preset == "balanced" else 60,
        "drawdown_warning": 0.08 if policy.preset == "conservative" else 0.12 if policy.preset == "balanced" else 0.18,
        "emergency_risk_off": 0.14 if policy.preset == "conservative" else 0.20 if policy.preset == "balanced" else 0.28,
    }


def risk_policy_to_dict(policy: RiskPolicy) -> dict[str, Any]:
    """Serialize the canonical policy to a JSON-friendly dict with stable casing."""

    raw = asdict(policy)
    return _camelize(raw)


def _camelize(value: Any) -> Any:
    if isinstance(value, dict):
        return {_snake_to_camel(key): _camelize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def _snake_to_camel(name: str) -> str:
    if "_" not in name:
        return name
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def validate_custom_policy(raw: dict[str, Any]) -> RiskPolicy:
    """Build a Custom policy from a dict, rejecting impossible ladders.

    Each ladder must be strictly increasing: target < warning < hardBuyBlock < urgentReview < extreme.
    """

    base = BALANCED
    try:
        s = raw.get("singleStock") or {}
        single = SingleStockPolicy(
            target=float(s.get("target", base.single_stock.target)),
            warning=float(s.get("warning", base.single_stock.warning)),
            hard_buy_block=float(s.get("hardBuyBlock", base.single_stock.hard_buy_block)),
            urgent_review=float(s.get("urgentReview", base.single_stock.urgent_review)),
            extreme=float(s.get("extreme", base.single_stock.extreme)),
        )
        ladder = (
            single.target,
            single.warning,
            single.hard_buy_block,
            single.urgent_review,
            single.extreme,
        )
        if not all(0 < ladder[i] < ladder[i + 1] for i in range(len(ladder) - 1)):
            raise ValueError(
                "Single-stock ladder must be strictly increasing: target < warning < hardBuyBlock < urgentReview < extreme."
            )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid single-stock policy: {exc}") from exc

    sector = raw.get("sector") or {}
    sector_policy = SectorPolicy(
        warning=float(sector.get("warning", base.sector.warning)),
        hard_cap=float(sector.get("hardCap", base.sector.hard_cap)),
        use_benchmark_relative_cap=bool(sector.get("useBenchmarkRelativeCap", base.sector.use_benchmark_relative_cap)),
        max_active_overweight=float(sector.get("maxActiveOverweight", base.sector.max_active_overweight)),
    )
    if not (0 < sector_policy.warning <= sector_policy.hard_cap < 1):
        raise ValueError("Sector ladder must satisfy 0 < warning <= hardCap < 1.")

    return replace(
        base,
        id=str(raw.get("id") or "custom"),
        name=str(raw.get("name") or "Custom"),
        preset="custom",
        single_stock=single,
        sector=sector_policy,
    )


def selected_risk_policy(conn) -> RiskPolicy:
    """Read the canonical policy out of risk_rules; default to balanced.

    The persisted preset key is ``risk_policy_preset``. If a future custom-policy
    feature stores a JSON blob under ``risk_policy_custom``, it is parsed and validated.
    """

    from app.database import get_risk_rules

    rules = get_risk_rules(conn)
    preset = str(rules.get("risk_policy_preset") or "balanced").lower()
    if preset == "custom":
        raw = rules.get("risk_policy_custom") or {}
        if isinstance(raw, dict) and raw:
            try:
                return validate_custom_policy(raw)
            except ValueError:
                return BALANCED
    return get_policy(preset)
