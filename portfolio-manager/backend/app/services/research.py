from __future__ import annotations

from typing import Any


def make_rules_based_memo(candidate: dict[str, Any], recommendation: dict[str, Any], macro: dict[str, Any]) -> dict[str, Any]:
    symbol = candidate["symbol"]
    action = recommendation["action"].lower()
    flags = recommendation.get("risk_flags", [])
    flag_text = " ".join(flags) if flags else "No hard risk-rule breach was detected."
    macro_bias = macro.get("risk_bias", "maintain diversified risk discipline")

    return {
        "symbol": symbol,
        "title": f"{symbol} {recommendation['action']} memo",
        "thesis": (
            f"{symbol} earns a {action} recommendation because its trend, risk-adjusted momentum, "
            f"liquidity, and quality profile score well against the current universe."
        ),
        "evidence": (
            f"Six-month momentum is {candidate['momentum_126d']:.1%}, annualized volatility is "
            f"{candidate['volatility']:.1%}, drawdown is {candidate['max_drawdown']:.1%}, and "
            f"quality score is {candidate['quality_score']:.2f}. Macro regime says: {macro_bias}."
        ),
        "risks": (
            f"{flag_text} Main risks are reversal after strong momentum, crowded positioning, "
            "macro regime changes, and correlation spikes during stress."
        ),
        "counterargument": (
            f"The case weakens if {symbol} is benefiting from a narrow temporary factor, if volatility "
            "rises faster than expected return, or if better ideas offer similar upside with lower drawdown."
        ),
        "change_mind": (
            "Downgrade if price falls below its intermediate trend, source data becomes stale, "
            "fundamentals deteriorate, or portfolio concentration rises above configured limits."
        ),
        "generation_method": "rules_based",
        "ai_provider": "",
        "ai_model": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def make_memo(candidate: dict[str, Any], recommendation: dict[str, Any], macro: dict[str, Any]) -> dict[str, Any]:
    return make_rules_based_memo(candidate, recommendation, macro)
