from __future__ import annotations

from collections import defaultdict
from typing import Any


STRATEGY_SLEEVES: list[dict[str, Any]] = [
    {
        "name": "Core broad-market equity",
        "category": "Core",
        "symbols": ["SPY", "VTI", "DIA", "RSP"],
        "goal": "Long-term compounding through broad US equity exposure.",
    },
    {
        "name": "Growth and momentum",
        "category": "Offense",
        "symbols": ["QQQ", "MTUM", "XLK", "SOXX", "ARKK", "NVDA", "MSFT"],
        "goal": "Capture persistent leadership and earnings momentum.",
    },
    {
        "name": "Quality compounders",
        "category": "Quality",
        "symbols": ["QUAL", "SCHD", "COST", "MSFT", "GOOGL", "BRK.B"],
        "goal": "Favor durable balance sheets, margins, and cash generation.",
    },
    {
        "name": "Value and dividends",
        "category": "Value",
        "symbols": ["VLUE", "SCHD", "DIA", "BRK.B", "JPM", "XLF"],
        "goal": "Seek cheaper cash-flow exposure and shareholder yield.",
    },
    {
        "name": "Small-cap recovery",
        "category": "Cyclical",
        "symbols": ["IWM", "RSP", "XLI", "XLB"],
        "goal": "Participate if market breadth and cyclical growth improve.",
    },
    {
        "name": "Defensive equity",
        "category": "Defense",
        "symbols": ["USMV", "XLP", "XLU", "XLV", "COST"],
        "goal": "Lower drawdown pressure while keeping equity exposure.",
    },
    {
        "name": "International developed markets",
        "category": "Global",
        "symbols": ["EFA", "VEA", "EWJ"],
        "goal": "Diversify beyond US valuation and currency exposure.",
    },
    {
        "name": "Emerging markets",
        "category": "Global",
        "symbols": ["EEM", "VWO", "INDA", "EWZ", "KWEB"],
        "goal": "Access higher-growth regions with higher volatility.",
    },
    {
        "name": "Treasury duration hedge",
        "category": "Hedge",
        "symbols": ["TLT", "IEF", "BND"],
        "goal": "Offset equity drawdowns when growth slows or rates fall.",
    },
    {
        "name": "Credit and income",
        "category": "Income",
        "symbols": ["LQD", "HYG", "BND", "SCHD"],
        "goal": "Generate income while monitoring credit-cycle risk.",
    },
    {
        "name": "Inflation and commodities",
        "category": "Macro Hedge",
        "symbols": ["GLD", "DBC", "SLV", "USO", "DBA", "TIP"],
        "goal": "Hedge inflation, currency debasement, and commodity shocks.",
    },
    {
        "name": "Real assets",
        "category": "Real Assets",
        "symbols": ["VNQ", "XLRE", "GLD", "TIP", "DBC"],
        "goal": "Diversify into inflation-sensitive tangible-asset exposure.",
    },
    {
        "name": "Currency diversifiers",
        "category": "Currency",
        "symbols": ["UUP", "FXE", "GLD"],
        "goal": "Track dollar and currency pressure that can change cross-asset returns.",
    },
    {
        "name": "Crypto and high-volatility optionality",
        "category": "Speculative",
        "symbols": ["IBIT", "BITO", "ARKK", "KWEB"],
        "goal": "Consider asymmetric upside only inside strict sizing limits.",
    },
]


def market_scope(conn) -> dict[str, Any]:
    rows = conn.execute("SELECT asset_class, sector, COUNT(*) AS count FROM instruments WHERE enabled = 1 GROUP BY asset_class, sector").fetchall()
    asset_classes: dict[str, int] = defaultdict(int)
    sectors: dict[str, int] = {}
    for row in rows:
        asset_classes[row["asset_class"]] += row["count"]
        sectors[row["sector"]] = row["count"]
    return {
        "enabled_instruments": sum(asset_classes.values()),
        "asset_classes": dict(asset_classes),
        "sectors": sectors,
        "strategy_count": len(STRATEGY_SLEEVES),
        "strategy_names": [item["name"] for item in STRATEGY_SLEEVES],
    }


def strategy_reviews(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_map = {item["symbol"]: item for item in features}
    reviews: list[dict[str, Any]] = []
    for sleeve in STRATEGY_SLEEVES:
        candidates = [feature_map[symbol] for symbol in sleeve["symbols"] if symbol in feature_map]
        if not candidates:
            continue
        score = sum(item["score"] for item in candidates) / len(candidates)
        confidence = sum(item["confidence"] for item in candidates) / len(candidates)
        risk_score = sum(item["risk_score"] for item in candidates) / len(candidates)
        momentum = sum(item["momentum_126d"] for item in candidates) / len(candidates)
        top_candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)[:3]
        if score > 0.10 and risk_score < 0.28:
            stance = "lean in"
        elif score > 0.03:
            stance = "selective"
        elif risk_score > 0.36:
            stance = "strict sizing"
        else:
            stance = "watch"
        reviews.append(
            {
                "name": sleeve["name"],
                "category": sleeve["category"],
                "goal": sleeve["goal"],
                "stance": stance,
                "score": round(score, 4),
                "confidence": round(confidence, 4),
                "risk_score": round(risk_score, 4),
                "momentum": round(momentum, 4),
                "candidates": [
                    {
                        "symbol": item["symbol"],
                        "name": item["name"],
                        "score": item["score"],
                        "confidence": item["confidence"],
                        "risk_score": item["risk_score"],
                    }
                    for item in top_candidates
                ],
            }
        )
    return sorted(reviews, key=lambda item: (item["score"] - item["risk_score"] * 0.35), reverse=True)
