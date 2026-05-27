def test_low_liquidity_blocks_candidate():
    from app.services.candidate_scoring import score_candidate
    from app.services.policy_engine import BALANCED

    candidate = {
        "symbol": "ILLIQ",
        "asset_class": "Stock",
        "sector": "Energy",
        "score": 0.2,
        "confidence": 0.5,
        "liquidity_score": 40,
        "risk_score": 0.3,
        "dollar_volume": 1_000_000,
        "annualized_vol": 0.30,
        "max_drawdown": -0.10,
        "data_freshness": "live",
    }
    score = score_candidate(candidate, BALANCED)
    assert any("dollar volume" in blocker.lower() or "liquidity" in blocker.lower() for blocker in score.blockers)


def test_high_volatility_blocks_candidate():
    from app.services.candidate_scoring import score_candidate
    from app.services.policy_engine import BALANCED

    candidate = {
        "symbol": "VOL",
        "asset_class": "Stock",
        "sector": "Energy",
        "score": 0.2,
        "confidence": 0.5,
        "liquidity_score": 80,
        "risk_score": 0.4,
        "dollar_volume": 20_000_000,
        "annualized_vol": 0.80,
        "max_drawdown": -0.10,
        "data_freshness": "live",
    }
    score = score_candidate(candidate, BALANCED)
    assert any("volatility" in blocker.lower() for blocker in score.blockers)


def test_deep_drawdown_blocks_candidate():
    from app.services.candidate_scoring import score_candidate
    from app.services.policy_engine import BALANCED

    candidate = {
        "symbol": "DD",
        "asset_class": "Stock",
        "sector": "Energy",
        "score": 0.2,
        "confidence": 0.5,
        "liquidity_score": 80,
        "risk_score": 0.4,
        "dollar_volume": 20_000_000,
        "annualized_vol": 0.30,
        "max_drawdown": -0.55,
        "data_freshness": "live",
    }
    score = score_candidate(candidate, BALANCED)
    assert any("drawdown" in blocker.lower() for blocker in score.blockers)


def test_limited_history_state_too_new():
    from app.services.candidate_scoring import score_candidate
    from app.services.policy_engine import BALANCED

    candidate = {
        "symbol": "IPO1",
        "asset_class": "Stock",
        "sector": "Technology",
        "score": 0.4,
        "confidence": 0.5,
        "liquidity_score": 80,
        "risk_score": 0.3,
        "dollar_volume": 30_000_000,
        "annualized_vol": 0.40,
        "max_drawdown": -0.10,
        "data_freshness": "live",
    }
    score = score_candidate(candidate, BALANCED, history_days=10)
    assert score.limited_history is not None
    assert score.limited_history.state == "too_new"
    assert any("watch-only" in blocker.lower() for blocker in score.blockers)


def test_limited_history_state_restricted():
    from app.services.candidate_scoring import score_candidate, classify_history
    from app.services.policy_engine import BALANCED

    classification = classify_history("MIDIPO", 100, BALANCED)
    assert classification.state == "restricted_signal"
    assert classification.requires_manual_review is False
    assert classification.max_initial_weight > 0


def test_stale_data_blocks_sizing():
    from app.services.candidate_scoring import score_candidate
    from app.services.policy_engine import BALANCED

    candidate = {
        "symbol": "STALE",
        "asset_class": "Stock",
        "sector": "Technology",
        "score": 0.3,
        "confidence": 0.6,
        "liquidity_score": 90,
        "risk_score": 0.3,
        "dollar_volume": 30_000_000,
        "annualized_vol": 0.30,
        "max_drawdown": -0.10,
        "data_freshness": "stale",
    }
    score = score_candidate(candidate, BALANCED)
    assert any("stale" in blocker.lower() for blocker in score.blockers)


def test_crypto_disabled_by_default_blocks_add():
    from app.services.candidate_scoring import score_candidate
    from app.services.policy_engine import BALANCED

    candidate = {
        "symbol": "BTC",
        "asset_class": "Stock",
        "sector": "Crypto",
        "score": 0.3,
        "confidence": 0.6,
        "liquidity_score": 95,
        "risk_score": 0.4,
        "dollar_volume": 1_000_000_000,
        "annualized_vol": 0.60,
        "max_drawdown": -0.30,
        "data_freshness": "live",
    }
    score = score_candidate(candidate, BALANCED, current_sector_weight=0.0)
    assert any("crypto" in blocker.lower() for blocker in score.blockers)


def test_thematic_etf_carries_penalty_not_blocker():
    from app.services.candidate_scoring import score_candidate
    from app.services.policy_engine import BALANCED

    candidate = {
        "symbol": "ARKK",
        "asset_class": "ETF",
        "is_thematic_etf": True,
        "sector": "Technology",
        "score": 0.2,
        "confidence": 0.6,
        "liquidity_score": 85,
        "risk_score": 0.4,
        "dollar_volume": 200_000_000,
        "annualized_vol": 0.30,
        "max_drawdown": -0.20,
        "data_freshness": "live",
    }
    score = score_candidate(candidate, BALANCED)
    assert any("thematic" in penalty.lower() for penalty in score.penalties)
    assert not any("crypto" in blocker.lower() for blocker in score.blockers)
