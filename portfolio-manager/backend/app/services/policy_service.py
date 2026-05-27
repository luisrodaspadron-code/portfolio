from __future__ import annotations

from typing import Any

from app.database import get_risk_rules, update_risk_rules
from app.services.policy_engine import (
    BALANCED,
    POLICY_VERSION,
    PRESET_DISPLAY,
    PRESETS,
    get_policy,
    legacy_rules_from_policy,
    risk_policy_to_dict,
    selected_risk_policy,
    validate_custom_policy,
)


OBJECTIVE_COPY = {
    "competition_growth": {
        "label": "Win the long-term competition",
        "description": "Prioritize aggressive compounding while keeping blow-up risk visible and constrained.",
    },
    "balanced_growth": {
        "label": "Grow steadily",
        "description": "Favor smoother growth and fewer concentration warnings.",
    },
    "capital_preservation": {
        "label": "Protect capital first",
        "description": "Make drawdown control and defensive exposure more important than upside.",
    },
}

RISK_COPY = {
    "aggressive_managed": {
        "label": "Aggressive but managed",
        "description": "Allow strong ideas, but cap single-position and sector risk.",
    },
    "moderate": {
        "label": "Moderate",
        "description": "Lower position sizes and warn earlier on drawdowns.",
    },
    "defensive": {
        "label": "Defensive",
        "description": "Smaller positions, tighter crypto/speculative caps, and faster risk-off alerts.",
    },
}

DIVERSIFICATION_COPY = {
    "broad_opportunistic": {
        "label": "Broad and opportunistic",
        "description": "Consider many strategies and let the advisor surface the strongest sleeves.",
    },
    "focused_best_ideas": {
        "label": "Focused best ideas",
        "description": "Permit fewer, larger high-conviction holdings.",
    },
    "highly_diversified": {
        "label": "Highly diversified",
        "description": "Prefer more holdings and lower concentration.",
    },
}

_OBJECTIVE_TO_PRESET = {
    "capital_preservation": "conservative",
    "balanced_growth": "balanced",
    "competition_growth": "competition",
}

_RISK_TO_PRESET = {
    "defensive": "conservative",
    "moderate": "balanced",
    "aggressive_managed": "aggressive",
}


def _preset_from_three_axis(objective: str, risk: str, diversification: str) -> str:
    """Pick a V8 preset closest to the legacy 3-axis combination."""

    if objective in _OBJECTIVE_TO_PRESET and risk == "aggressive_managed" and objective == "competition_growth":
        return "competition"
    if risk in _RISK_TO_PRESET:
        return _RISK_TO_PRESET[risk]
    return _OBJECTIVE_TO_PRESET.get(objective, "balanced")


def _policy_rules(objective: str, risk: str, diversification: str, *, preset_override: str | None = None) -> dict[str, Any]:
    preset_id = preset_override or _preset_from_three_axis(objective, risk, diversification)
    canonical = get_policy(preset_id)
    rules = legacy_rules_from_policy(canonical)
    rules.update(
        {
            "policy_objective": objective,
            "policy_risk": risk,
            "policy_diversification": diversification,
            "decision_cadence": "daily_weekly",
            "autopilot_enabled": False,
            "autopilot_interval_hours": 24,
            "real_money_trading_enabled": False,
            "risk_policy_preset": canonical.preset,
        }
    )

    if diversification == "focused_best_ideas":
        rules["max_positions"] = 12
    elif diversification == "highly_diversified":
        rules["max_positions"] = 28
    else:
        rules["max_positions"] = 18

    return rules


def policy_options() -> dict[str, Any]:
    return {
        "objectives": OBJECTIVE_COPY,
        "risks": RISK_COPY,
        "diversification": DIVERSIFICATION_COPY,
        "presets": PRESET_DISPLAY,
    }


def policy_status(conn) -> dict[str, Any]:
    rules = get_risk_rules(conn)
    objective = str(rules.get("policy_objective", "balanced_growth"))
    risk = str(rules.get("policy_risk", "moderate"))
    diversification = str(rules.get("policy_diversification", "broad_opportunistic"))
    canonical = selected_risk_policy(conn)
    return {
        "objective": objective,
        "risk": risk,
        "diversification": diversification,
        "summary": {
            "objective": OBJECTIVE_COPY.get(objective, OBJECTIVE_COPY["balanced_growth"]),
            "risk": RISK_COPY.get(risk, RISK_COPY["moderate"]),
            "diversification": DIVERSIFICATION_COPY.get(diversification, DIVERSIFICATION_COPY["broad_opportunistic"]),
        },
        "options": policy_options(),
        "guardrails": {
            "max_single_stock_weight": rules["max_single_stock_weight"],
            "max_etf_weight": rules["max_etf_weight"],
            "max_sector_weight": rules["max_sector_weight"],
            "max_crypto_weight": rules["max_crypto_weight"],
            "drawdown_warning": rules["drawdown_warning"],
            "emergency_risk_off": rules["emergency_risk_off"],
            "min_liquidity_score": rules["min_liquidity_score"],
            "max_positions": rules["max_positions"],
        },
        "policyVersion": POLICY_VERSION,
        "selectedPolicy": risk_policy_to_dict(canonical),
        "autopilotEnabled": bool(rules.get("autopilot_enabled", False)),
        "realMoneyTradingEnabled": bool(rules.get("real_money_trading_enabled", False)),
    }


def apply_policy(
    conn,
    objective: str,
    risk: str,
    diversification: str,
    *,
    preset: str | None = None,
    custom_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if objective not in OBJECTIVE_COPY:
        raise ValueError("Unknown objective policy.")
    if risk not in RISK_COPY:
        raise ValueError("Unknown risk policy.")
    if diversification not in DIVERSIFICATION_COPY:
        raise ValueError("Unknown diversification policy.")
    if preset and preset not in PRESETS and preset != "custom":
        raise ValueError(f"Unknown risk preset: {preset}")
    if preset == "custom":
        if not custom_policy:
            raise ValueError("Custom policy preset requires a custom_policy body.")
        validate_custom_policy(custom_policy)
    rules = _policy_rules(objective, risk, diversification, preset_override=preset)
    if preset == "custom" and custom_policy:
        rules["risk_policy_custom"] = custom_policy
    update_risk_rules(conn, rules)
    return policy_status(conn)
