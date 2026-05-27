from __future__ import annotations

from typing import Any

from app.database import get_risk_rules, update_risk_rules


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


def _policy_rules(objective: str, risk: str, diversification: str) -> dict[str, Any]:
    rules: dict[str, Any] = {
        "policy_objective": objective,
        "policy_risk": risk,
        "policy_diversification": diversification,
        "decision_cadence": "daily_weekly",
        "autopilot_enabled": True,
        "autopilot_interval_hours": 24,
        "real_money_trading_enabled": False,
    }

    if risk == "aggressive_managed":
        rules.update(
            {
                "max_single_stock_weight": 0.08,
                "max_etf_weight": 0.25,
                "max_sector_weight": 0.30,
                "max_crypto_weight": 0.05,
                "drawdown_warning": 0.12,
                "emergency_risk_off": 0.20,
                "min_liquidity_score": 65,
            }
        )
    elif risk == "moderate":
        rules.update(
            {
                "max_single_stock_weight": 0.06,
                "max_etf_weight": 0.20,
                "max_sector_weight": 0.25,
                "max_crypto_weight": 0.03,
                "drawdown_warning": 0.09,
                "emergency_risk_off": 0.16,
                "min_liquidity_score": 70,
            }
        )
    else:
        rules.update(
            {
                "max_single_stock_weight": 0.04,
                "max_etf_weight": 0.16,
                "max_sector_weight": 0.20,
                "max_crypto_weight": 0.01,
                "drawdown_warning": 0.06,
                "emergency_risk_off": 0.12,
                "min_liquidity_score": 75,
            }
        )

    if objective == "capital_preservation":
        rules["drawdown_warning"] = min(rules["drawdown_warning"], 0.06)
        rules["emergency_risk_off"] = min(rules["emergency_risk_off"], 0.12)
        rules["max_crypto_weight"] = min(rules["max_crypto_weight"], 0.01)
    elif objective == "balanced_growth":
        rules["max_single_stock_weight"] = min(rules["max_single_stock_weight"], 0.06)
        rules["max_sector_weight"] = min(rules["max_sector_weight"], 0.25)

    if diversification == "focused_best_ideas":
        rules["max_positions"] = 12
        rules["max_single_stock_weight"] = min(rules["max_single_stock_weight"] + 0.02, 0.10)
        rules["max_etf_weight"] = min(rules["max_etf_weight"] + 0.05, 0.30)
    elif diversification == "highly_diversified":
        rules["max_positions"] = 28
        rules["max_single_stock_weight"] = min(rules["max_single_stock_weight"], 0.05)
        rules["max_etf_weight"] = min(rules["max_etf_weight"], 0.18)
        rules["max_sector_weight"] = min(rules["max_sector_weight"], 0.22)
    else:
        rules["max_positions"] = 18

    return rules


def policy_options() -> dict[str, Any]:
    return {
        "objectives": OBJECTIVE_COPY,
        "risks": RISK_COPY,
        "diversification": DIVERSIFICATION_COPY,
    }


def policy_status(conn) -> dict[str, Any]:
    rules = get_risk_rules(conn)
    objective = str(rules.get("policy_objective", "competition_growth"))
    risk = str(rules.get("policy_risk", "aggressive_managed"))
    diversification = str(rules.get("policy_diversification", "broad_opportunistic"))
    return {
        "objective": objective,
        "risk": risk,
        "diversification": diversification,
        "summary": {
            "objective": OBJECTIVE_COPY.get(objective, OBJECTIVE_COPY["competition_growth"]),
            "risk": RISK_COPY.get(risk, RISK_COPY["aggressive_managed"]),
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
    }


def apply_policy(conn, objective: str, risk: str, diversification: str) -> dict[str, Any]:
    if objective not in OBJECTIVE_COPY:
        raise ValueError("Unknown objective policy.")
    if risk not in RISK_COPY:
        raise ValueError("Unknown risk policy.")
    if diversification not in DIVERSIFICATION_COPY:
        raise ValueError("Unknown diversification policy.")
    update_risk_rules(conn, _policy_rules(objective, risk, diversification))
    return policy_status(conn)
