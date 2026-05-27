from fastapi.testclient import TestClient
import time


def test_clean_install_acceptance_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["paper_portfolio"]["cash"] == 100000
        assert dashboard.json()["policy"]["summary"]["objective"]["label"] == "Grow steadily"

        policy = client.put(
            "/api/settings/policy",
            json={
                "objective": "competition_growth",
                "risk": "moderate",
                "diversification": "highly_diversified",
            },
        )
        assert policy.status_code == 200
        guardrails = policy.json()["policy"]["guardrails"]
        assert guardrails["max_single_stock_weight"] == 0.15
        assert guardrails["max_etf_weight"] == 0.60
        assert guardrails["max_positions"] == 28

        updated_dashboard = client.get("/api/dashboard")
        assert updated_dashboard.status_code == 200
        assert updated_dashboard.json()["policy"]["risk"] == "moderate"
        assert updated_dashboard.json()["risk_rules"]["max_positions"] == 28

        refresh = client.post("/api/data/refresh")
        assert refresh.status_code == 200
        assert refresh.json()["counts"]["price_bars"] > 0

        recs = client.post("/api/recommendations/run", json={"max_ideas": 5})
        assert recs.status_code == 200
        assert len(recs.json()["recommendations"]) == 5

        order = client.post("/api/portfolio/paper-order", json={"symbol": "SPY", "side": "buy", "quantity": 5})
        assert order.status_code == 200
        assert order.json()["positions"][0]["symbol"] == "SPY"

        backtest = client.post("/api/backtests", json={"symbols": ["SPY", "QQQ", "TLT", "GLD"], "max_positions": 3})
        assert backtest.status_code == 200
        backtest_payload = backtest.json()
        assert backtest_payload["metrics"]["total_return"] != 0
        assert "sortino" in backtest_payload["metrics"]
        assert "calmar" in backtest_payload["metrics"]
        assert "benchmark_relative_return" in backtest_payload["metrics"]
        assert backtest_payload["params"]["validation"]["no_lookahead"] is True
        assert backtest_payload["params"]["validation"]["benchmark_symbol"] == "SPY"

        csv_body = b"symbol,quantity,avg_cost\nAAPL,2,180\nMSFT,3,410\n"
        upload = client.post(
            "/api/import/holdings-csv",
            files={"file": ("holdings.csv", csv_body, "text/csv")},
        )
        assert upload.status_code == 200
        assert len(upload.json()["imported"]) == 2
        assert upload.json()["status"] == "success"

        memos = client.get("/api/research/memos")
        assert memos.status_code == 200
        assert memos.json()["memos"]


def test_headerless_holdings_imports_fractional_shares(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    csv_body = b"CCJ,30.072,116.917\nMETA,43,604.257\nMSFT,2.3337,428.50\nNEE,80.2258,81.769\nNVDA,5.3832,0.00\nRTX,33.9719,195.75\nVST,24.9364,152.387\n"
    with TestClient(app) as client:
        upload = client.post(
            "/api/import/holdings-csv",
            files={"file": ("holdings.csv", csv_body, "text/csv")},
        )
        assert upload.status_code == 200
        payload = upload.json()
        assert payload["status"] in {"success", "partial"}
        assert payload["detected_columns"]["symbol"] == "column_1"
        imported = {item["symbol"]: item for item in payload["imported"]}
        assert set(imported) == {"CCJ", "META", "MSFT", "NEE", "NVDA", "RTX", "VST"}
        assert imported["CCJ"]["quantity"] == 30.072
        assert imported["NVDA"]["quantity"] == 5.3832
        assert payload["portfolio"]["positions"]
        assert all("valuation_status" in position for position in payload["portfolio"]["positions"])

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        trend = dashboard.json()["portfolio_trend"]
        assert trend["granularity"] == "daily"
        assert "day_change" in trend
        assert isinstance(trend["position_changes"], list)


def test_async_advisor_run_records_real_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app
    from app.services import advisor_service

    monkeypatch.setattr(
        advisor_service,
        "refresh_universe",
        lambda conn: {"universe": {"included_assets": 250, "scope_label": "250 tradable assets checked"}, "providers": []},
    )
    monkeypatch.setattr(
        advisor_service,
        "refresh_data",
        lambda force_sample=False: {
            "counts": {"price_bars": 250, "priced_symbols": 250},
            "providers": [{"provider": "alpaca", "status": "success", "records": 250}],
            "message": "Prices checked.",
        },
    )
    monkeypatch.setattr(
        advisor_service,
        "portfolio_summary",
        lambda conn, mode="real": {
            "id": 1,
            "cash": 0,
            "total_value": 10000,
            "positions": [{"symbol": "MSFT", "quantity": 2, "weight": 0.08}],
        },
    )
    monkeypatch.setattr(
        advisor_service,
        "run_recommendations",
        lambda conn, payload: {"recommendations": [{"action": "BUY"}, {"action": "WATCH"}]},
    )
    monkeypatch.setattr(
        advisor_service,
        "run_backtest",
        lambda conn, payload: {"id": 7, "metrics": {"total_return": 0.2, "max_drawdown": -0.08, "sharpe": 1.1}},
    )
    monkeypatch.setattr(
        advisor_service,
        "quant_diagnostics",
        lambda conn: {"status": "healthy", "recommendations": {"total": 2}, "checks": [{"name": "risk", "status": "pass"}]},
    )
    monkeypatch.setattr(advisor_service, "compute_universe_features", lambda conn: [{"symbol": "MSFT"}])
    monkeypatch.setattr(advisor_service, "strategy_reviews", lambda features: [{"name": "Momentum"}])
    monkeypatch.setattr(
        advisor_service,
        "run_advisor_decision",
        lambda conn, force=True: {
            "status": "success",
            "id": 11,
            "portfolio_verdict": "Hold current positions and stagger only eligible adds.",
            "model": "gpt-5-mini",
            "total_tokens": 321,
            "packet_hash": "packet-123",
            "fallback_reason": "",
            "response_id": "resp_123",
            "holding_decisions": [{"symbol": "MSFT", "decision": "Hold"}],
            "opportunity_decisions": [{"symbol": "SPY", "decision": "Stagger Entry"}],
        },
    )

    with TestClient(app) as client:
        started = client.post("/api/advisor/runs")
        assert started.status_code == 200
        run_id = started.json()["run_id"]

        detail = None
        for _ in range(40):
            response = client.get(f"/api/advisor/runs/{run_id}")
            assert response.status_code == 200
            detail = response.json()
            if detail["status"] != "running":
                break
            time.sleep(0.05)

    assert detail is not None
    assert detail["status"] == "success"
    assert detail["reasoning"] == "medium"
    assert detail["token_usage"] == 321
    assert detail["universe_size"] == 250
    assert detail["priced_symbols"] == 250
    assert detail["decision_hash"] == "packet-123"
    step_names = [step["step"] for step in detail["steps"]]
    assert "AI review generated" in step_names
    assert "Decision summary created" in step_names
    assert any(event["phase"] == "llm" and event["status"] == "success" for event in detail["events"])
    assert any(event["phase"] == "receipt" for event in detail["events"])

    # V8: the SSE bus must have emitted matching lifecycle events for the same run.
    from app.services import run_events

    bus_events = run_events.history_as_dicts(run_id)
    assert bus_events, "Run event bus did not record any events for the completed cycle."
    types_seen = {event["type"] for event in bus_events}
    assert "run" in types_seen and "step" in types_seen
    # First and last bus events must be the run lifecycle markers.
    assert bus_events[0]["type"] == "run" and bus_events[0]["status"] == "running"
    assert bus_events[-1]["type"] == "run" and bus_events[-1]["status"] in {"success", "failed"}
    # Step events must be a superset of the durable step rows.
    bus_step_titles = {event["title"] for event in bus_events if event["type"] == "step"}
    assert "AI review generated" in bus_step_titles
    assert "Decision summary created" in bus_step_titles
