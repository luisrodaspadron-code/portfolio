from app.database import DEFAULT_RISK_RULES
from app.services.risk import evaluate_candidate, target_weight_for_candidate


def test_risk_gate_blocks_oversized_crypto_proxy():
    candidate = {
        "symbol": "BITO",
        "asset_class": "ETF",
        "sector": "Crypto Proxy",
        "liquidity_score": 70,
        "risk_score": 0.3,
        "score": 0.3,
        "confidence": 0.8,
    }

    status, flags = evaluate_candidate(candidate, 0.12, DEFAULT_RISK_RULES)

    assert status == "watch"
    assert any("crypto" in flag.lower() for flag in flags)


def test_target_weight_respects_single_stock_cap():
    candidate = {
        "symbol": "NVDA",
        "asset_class": "Stock",
        "sector": "Technology",
        "score": 0.7,
        "confidence": 0.9,
    }

    assert target_weight_for_candidate(candidate, DEFAULT_RISK_RULES) <= DEFAULT_RISK_RULES["max_single_stock_weight"]
