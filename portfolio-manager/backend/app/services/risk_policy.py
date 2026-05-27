"""Legacy shim that re-exports the canonical V8 policy values.

The canonical engine is :mod:`app.services.policy_engine`. This module remains for
backwards compatibility with code paths that still read flat ``rules`` dicts
populated from the database; new code should call
``policy_engine.selected_risk_policy(conn)`` directly.
"""

from __future__ import annotations

from typing import Any

from app.services.policy_engine import (
    BALANCED,
    POLICY_VERSION,
    PRESETS,
    legacy_rules_from_policy,
)

LEGACY_POLICY_VERSION = "risk-policy.v1"


def _balanced_legacy() -> dict[str, Any]:
    rules = legacy_rules_from_policy(BALANCED)
    rules.update(
        {
            "base_currency": "USD",
            "real_money_trading_enabled": False,
            "decision_cadence": "daily_weekly",
            "autopilot_enabled": False,
            "autopilot_interval_hours": 24,
            "policy_objective": "balanced_growth",
            "policy_risk": "moderate",
            "policy_diversification": "broad_opportunistic",
            "risk_policy_preset": "balanced",
            "risk_policy_custom": None,
        }
    )
    return rules


DEFAULT_RISK_RULES: dict[str, Any] = _balanced_legacy()

DEFAULT_RISK_POLICY: dict[str, Any] = {
    "maxSingleStockWeight": BALANCED.single_stock.urgent_review,
    "maxSectorWeight": BALANCED.sector.hard_cap,
    "maxCryptoWeight": BALANCED.crypto.max_total,
    "maxSingleCryptoWeight": BALANCED.crypto.max_single,
    "maxIlliquidPositionWeight": BALANCED.single_new_stock_add.initial_max,
    "maxNewPositionWeight": BALANCED.single_new_stock_add.initial_max,
    "minPriceFreshnessSecondsEquityLive": BALANCED.data_quality.equity_live_seconds,
    "minPriceFreshnessSecondsEquityRecent": BALANCED.data_quality.equity_recent_seconds,
    "minPriceFreshnessSecondsCryptoLive": BALANCED.data_quality.crypto_live_seconds,
    "minHistoryDaysForFullSignal": BALANCED.data_quality.min_history_days_full,
    "minHistoryDaysForRestrictedSignal": BALANCED.data_quality.min_history_days_restricted,
    "minDollarVolume": BALANCED.liquidity.min_dollar_volume_default,
    "maxStandaloneDrawdownForAdd": 0.25,
    "maxAnnualizedVolForAdd": 0.60,
    "targetTranchesDefault": BALANCED.remediation.default_tranches,
    "targetTranchesMin": BALANCED.remediation.min_tranches,
    "targetTranchesMax": BALANCED.remediation.max_tranches,
}

RISK_PRESETS: dict[str, dict[str, float]] = {
    name: {
        "max_single_stock_weight": policy.single_stock.urgent_review,
        "max_sector_weight": policy.sector.hard_cap,
    }
    for name, policy in PRESETS.items()
}

__all__ = [
    "POLICY_VERSION",
    "LEGACY_POLICY_VERSION",
    "DEFAULT_RISK_RULES",
    "DEFAULT_RISK_POLICY",
    "RISK_PRESETS",
]
