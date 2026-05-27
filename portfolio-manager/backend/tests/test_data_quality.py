from datetime import datetime, timezone


def test_freshness_from_age_uses_policy_thresholds():
    from app.services.data_quality_service import freshness_from_age
    from app.services.policy_engine import BALANCED

    assert freshness_from_age(60, policy=BALANCED) == "live"
    assert freshness_from_age(BALANCED.data_quality.equity_live_seconds + 1, policy=BALANCED) == "recent"
    assert freshness_from_age(BALANCED.data_quality.equity_recent_seconds + 1, policy=BALANCED) == "stale"
    assert freshness_from_age(None, policy=BALANCED) == "missing"


def test_crypto_freshness_uses_crypto_thresholds():
    from app.services.data_quality_service import freshness_from_age
    from app.services.policy_engine import BALANCED

    assert freshness_from_age(60, policy=BALANCED, asset_class="crypto") == "live"
    assert (
        freshness_from_age(BALANCED.data_quality.crypto_live_seconds + 1, policy=BALANCED, asset_class="crypto")
        == "recent"
    )


def test_provider_mode_for_prices_requires_non_sample_source():
    from app.services.data_quality_service import provider_mode_for_prices
    from app.services.policy_engine import BALANCED

    now = datetime(2026, 5, 27, 16, 0, tzinfo=timezone.utc)
    # sample-only data should not return "live"
    mode = provider_mode_for_prices(
        "2026-05-27T15:55:00+00:00",
        {"sample": 10_000},
        policy=BALANCED,
        now=now,
    )
    assert mode == "partial"


def test_provider_mode_for_prices_returns_live_with_fresh_non_sample():
    from app.services.data_quality_service import provider_mode_for_prices
    from app.services.policy_engine import BALANCED

    now = datetime(2026, 5, 27, 16, 0, tzinfo=timezone.utc)
    mode = provider_mode_for_prices(
        "2026-05-27T15:55:00+00:00",
        {"alpaca": 50_000, "sample": 100},
        policy=BALANCED,
        now=now,
    )
    assert mode == "live"


def test_provider_mode_for_prices_returns_stale_when_old():
    from app.services.data_quality_service import provider_mode_for_prices
    from app.services.policy_engine import BALANCED

    now = datetime(2026, 5, 27, 16, 0, tzinfo=timezone.utc)
    mode = provider_mode_for_prices(
        "2026-05-25T15:55:00+00:00",
        {"alpaca": 50_000, "sample": 100},
        policy=BALANCED,
        now=now,
    )
    assert mode == "stale"


def test_provider_mode_missing_when_no_timestamp():
    from app.services.data_quality_service import provider_mode_for_prices
    from app.services.policy_engine import BALANCED

    assert provider_mode_for_prices(None, {}, policy=BALANCED) == "missing"


def test_build_source_matrix_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.data_quality_service import build_source_matrix

    init_db()
    with get_conn() as conn:
        matrix = build_source_matrix(conn)
    assert "prices" in matrix["matrix"]
    assert "fundamentals" in matrix["matrix"]
    assert "telemetry" in matrix["matrix"]
    assert matrix["selectedPreset"] == "balanced"
    assert matrix["matrix"]["events"]["usedInRun"] is False
