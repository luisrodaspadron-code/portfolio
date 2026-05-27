from __future__ import annotations

from typing import Any


def evaluate_candidate(candidate: dict[str, Any], target_weight: float, rules: dict[str, Any]) -> tuple[str, list[str]]:
    flags: list[str] = []
    asset_class = candidate.get("asset_class")
    sector = candidate.get("sector", "Unknown")
    symbol = candidate.get("symbol", "")
    liquidity = candidate.get("liquidity_score", 0)
    risk_score = candidate.get("risk_score", 1.0)

    if liquidity < rules["min_liquidity_score"]:
        flags.append(f"{symbol} liquidity score is below the configured floor.")
    if asset_class == "Stock" and target_weight > rules["max_single_stock_weight"]:
        flags.append(f"{symbol} would exceed the single-stock cap.")
    if asset_class == "ETF" and target_weight > rules["max_etf_weight"]:
        flags.append(f"{symbol} would exceed the ETF cap.")
    if "Crypto" in sector and target_weight > rules["max_crypto_weight"]:
        flags.append(f"{symbol} would exceed the crypto/direct commodity cap.")
    if risk_score > 0.42:
        flags.append(f"{symbol} has elevated standalone volatility/drawdown risk.")

    status = "pass" if not flags else "watch"
    if liquidity < rules["min_liquidity_score"] * 0.75 or risk_score > 0.68:
        status = "fail"
    return status, flags


def target_weight_for_candidate(candidate: dict[str, Any], rules: dict[str, Any]) -> float:
    score = max(candidate.get("score", 0), 0)
    base = min(0.02 + score * 0.22 + candidate.get("confidence", 0.4) * 0.05, 0.16)
    if candidate.get("asset_class") == "ETF":
        cap = rules["max_etf_weight"]
    else:
        cap = rules["max_single_stock_weight"]
    if "Crypto" in candidate.get("sector", ""):
        cap = min(cap, rules["max_crypto_weight"])
    return round(max(0.01, min(base, cap)), 4)
