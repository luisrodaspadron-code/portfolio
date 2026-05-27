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
    assert "liquidity" in matrix["matrix"]
    assert "fundamentals" in matrix["matrix"]
    assert "filings" in matrix["matrix"]
    assert "portfolioState" in matrix["matrix"]
    assert "ai" in matrix["matrix"]
    assert "telemetry" in matrix["matrix"]
    assert matrix["selectedPreset"] == "balanced"
    assert matrix["matrix"]["events"]["usedInRun"] is False
    for entry in matrix["matrix"].values():
        assert 0 <= entry["confidence"] <= 1
        assert "usedInLatestRun" in entry


def test_source_matrix_maps_research_agenda_data_classes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.data_quality_service import build_source_matrix
    from app.services.portfolio_service import import_holdings_csv

    init_db()
    with get_conn() as conn:
        import_holdings_csv(conn, b"META,2,604.25\nMSFT,1,428.50\n")
        source_matrix = build_source_matrix(conn)

    rows = source_matrix["matrix"]
    # Paper requirement: expose the seven major data classes as explicit,
    # auditable rows instead of collapsing them into one generic status.
    assert {"prices", "liquidity"}.issubset(rows)
    assert {"fundamentals", "filings"}.issubset(rows)
    assert {"macro", "factors", "events", "ipoCalendar", "portfolioState", "telemetry", "ai"}.issubset(rows)
    assert rows["portfolioState"]["usedInRun"] is True
    assert rows["portfolioState"]["coverage"] == "complete"
    assert rows["ai"]["fallback"] == "quant_only"
    assert "openai_api_key" not in str(rows["ai"]).lower()
    coverage = source_matrix["summary"]["requiredClassesCovered"]
    assert coverage["portfolioUserState"] is True
    assert coverage["telemetryAudit"] is True


def test_source_matrix_does_not_cross_label_price_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.data_quality_service import build_source_matrix

    init_db()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO instruments (symbol, name, asset_class, sector) VALUES (?, ?, ?, ?)",
            ("ZZZ", "Provider Test Inc.", "Stock", "Technology"),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO price_bars
            (symbol, date, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ZZZ", "2026-05-27T15:55:00+00:00", 10, 11, 9, 10.5, 2_000_000, "alpaca"),
        )
        conn.execute(
            """
            INSERT INTO provider_refreshes (provider, status, started_at, finished_at, records, message, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("sec_edgar", "success", "2026-05-27T15:59:00+00:00", "2026-05-27T16:00:00+00:00", 1, "SEC refresh", ""),
        )
        matrix = build_source_matrix(conn)

    assert matrix["matrix"]["prices"]["provider"] == "alpaca"
    assert matrix["matrix"]["liquidity"]["provider"] == "alpaca"
