import json

from fastapi.testclient import TestClient


def test_alpaca_universe_ingestion_handles_active_tradable_and_ipo(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.providers.base import ProviderStatus
    from app.services import universe_service

    class FakeAlpacaProvider:
        name = "alpaca"

        def __init__(self, settings):
            self.settings = settings

        def status(self):
            return ProviderStatus(name="alpaca", configured=True, capabilities=["assets"], note="test", priority=100)

        async def assets(self):
            return [
                {
                    "symbol": "ABC",
                    "name": "ABC Corp",
                    "asset_class": "us_equity",
                    "exchange": "NASDAQ",
                    "status": "active",
                    "tradable": True,
                    "marginable": True,
                    "shortable": True,
                    "fractionable": True,
                    "attributes": ["ipo"],
                },
                {
                    "symbol": "XYZ",
                    "name": "XYZ Corp",
                    "asset_class": "us_equity",
                    "exchange": "NYSE",
                    "status": "inactive",
                    "tradable": False,
                },
            ]

    monkeypatch.setattr(universe_service, "AlpacaProvider", FakeAlpacaProvider)

    from app.database import get_conn, init_db
    from app.services.universe_service import refresh_universe

    init_db()
    with get_conn() as conn:
        result = refresh_universe(conn)
        abc = conn.execute("SELECT * FROM universe_assets WHERE symbol = 'ABC'").fetchone()
        xyz = conn.execute("SELECT * FROM universe_assets WHERE symbol = 'XYZ'").fetchone()

    assert result["providers"][0]["status"] == "success"
    assert abc["included"] == 1
    assert abc["is_ipo"] == 1
    assert xyz["included"] == 0
    assert "tradable" in xyz["exclusion_reason"].lower()


def test_sec_ticker_mapping_adds_dynamic_ciks(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("SEC_USER_AGENT", "Signal PM test contact@example.org")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.providers.base import ProviderStatus
    from app.services import universe_service

    class FakeSecProvider:
        name = "sec_edgar"

        def __init__(self, settings):
            self.settings = settings

        def status(self):
            return ProviderStatus(name="sec_edgar", configured=True, capabilities=["company_tickers"], note="test", priority=70)

        async def company_tickers(self):
            return {"0": {"ticker": "ABC", "cik_str": 123456, "title": "ABC Corp"}}

    monkeypatch.setattr(universe_service, "SecEdgarProvider", FakeSecProvider)

    from app.database import get_conn, init_db
    from app.services.universe_service import refresh_universe

    init_db()
    with get_conn() as conn:
        result = refresh_universe(conn)
        row = conn.execute("SELECT * FROM universe_assets WHERE symbol = 'ABC'").fetchone()

    assert result["providers"][1]["status"] == "success"
    assert row["cik"] == "123456"
    assert row["included"] == 0


def test_advisor_decision_prompt_and_risk_gate_enforcement(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import decision_service

    seen_payloads = []

    def fake_response(payload, api_key):
        seen_payloads.append(payload)
        context = json.loads(payload["input"])
        assert api_key == "test-key"
        assert "risk_gates" in {tool["name"] for tool in context["tool_inventory"]}
        assert "market_universe" in context
        assert "deterministic_decision" in context
        first_opportunity = context["deterministic_decision"]["opportunity_decisions"][0]
        return {
            "id": "resp_decision",
            "output_text": json.dumps(
                {
                    "portfolio_verdict": "Keep the portfolio mostly intact, but stage one eligible add.",
                    "holding_decisions": context["deterministic_decision"]["holding_decisions"],
                    "opportunity_decisions": [
                        {
                            **first_opportunity,
                            "decision": "Add" if first_opportunity["eligibility"] == "fail" else "Stagger Entry",
                            "ai_commentary": "AI reviewed quant evidence and source freshness.",
                        }
                    ],
                    "execution_plan": ["Use 3 tranches.", "No automatic trades."],
                    "staggering_guidance": ["Stage entries unless data turns stale."],
                    "entry_conditions": ["Fresh data and risk gates must still pass."],
                    "risks": ["Sample data lowers confidence."],
                    "data_used": ["advisor packet", "risk gates", "market universe"],
                    "missing_data": [],
                    "what_would_change_my_mind": ["Risk gate failure."],
                }
            ),
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        }

    monkeypatch.setattr(decision_service, "_call_openai_response", fake_response)

    from app.database import get_conn
    from app.main import app
    from app.services.portfolio_service import import_holdings_csv

    with TestClient(app) as client:
        with get_conn() as conn:
            import_holdings_csv(conn, b"MSFT,2,428.50\nMETA,2,604.25\n")
        response = client.post("/api/advisor/decision")

    assert response.status_code == 200
    decision = response.json()["advisor_decision"]
    assert seen_payloads[0]["model"] == "gpt-5.5"
    assert seen_payloads[0]["reasoning"] == {"effort": "medium"}
    assert decision["status"] == "success"
    assert decision["holding_decisions"]
    assert decision["portfolio_verdict"].startswith("Keep")
    assert decision["total_tokens"] == 150
    assert all(item["decision"] in {"Hold", "Add", "Trim", "Rotate", "Stagger Entry", "Avoid", "Wait For Data"} for item in decision["opportunity_decisions"])


def test_malformed_ai_decision_falls_back_safely(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import decision_service

    def malformed(payload, api_key):
        return {"id": "bad", "output_text": "{not-json", "usage": {"total_tokens": 1}}

    monkeypatch.setattr(decision_service, "_call_openai_response", malformed)

    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/advisor/decision")

    assert response.status_code == 200
    decision = response.json()["advisor_decision"]
    assert decision["status"] == "fallback"
    assert decision["portfolio_verdict"]
    assert decision["fallback_reason"]


def test_rules_based_decision_persists_trim_receipt_math(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    csv_body = (
        b"CCJ,30.072,116.917\n"
        b"META,43,604.257\n"
        b"MSFT,2.3337,428.50\n"
        b"NEE,80.2258,81.769\n"
        b"NVDA,5.3832,0.00\n"
        b"RTX,33.9719,195.75\n"
        b"VST,24.9364,152.387\n"
    )
    with TestClient(app) as client:
        upload = client.post("/api/import/holdings-csv", files={"file": ("holdings.csv", csv_body, "text/csv")})
        assert upload.status_code == 200
        response = client.post("/api/advisor/decision")

    assert response.status_code == 200
    decision = response.json()["advisor_decision"]
    meta = next(item for item in decision["holding_decisions"] if item["symbol"] == "META")
    assert meta["decision"] == "Trim"
    assert meta["reason_code"] == "SINGLE_NAME_CAP_BREACH"
    assert meta["detail_payload"]["advisoryOnly"] is True
    assert meta["detail_payload"]["capDistance"]["breached"] is True
    assert meta["detail_payload"]["trimPlan"]["advisoryOnly"] is True
    assert meta["detail_payload"]["trimPlan"]["targetValue"] > 0
    assert meta["detail_payload"]["trimPlan"]["estimatedSellValue"] > 0
    assert "No real trades are placed" in decision["execution_plan"][0]


def test_canonical_advisor_packet_surfaces_sample_portfolio_first_action(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    csv_body = (
        b"CCJ,30.072,116.917\n"
        b"META,43,604.257\n"
        b"MSFT,2.3337,428.50\n"
        b"NEE,80.2258,81.769\n"
        b"NVDA,5.3832,0.00\n"
        b"RTX,33.9719,195.75\n"
        b"VST,24.9364,152.387\n"
    )
    with TestClient(app) as client:
        upload = client.post("/api/import/holdings-csv", files={"file": ("holdings.csv", csv_body, "text/csv")})
        assert upload.status_code == 200
        decision_response = client.post("/api/advisor/decision")
        assert decision_response.status_code == 200
        packet_response = client.get("/api/advisor/packet/canonical")

    assert packet_response.status_code == 200
    packet = packet_response.json()["advisor_packet"]
    first_action = packet["recommendedPriority"]["firstAction"]
    assert packet["packetVersion"] == "signal-prime.v1"
    assert first_action["symbol"] == "META"
    assert first_action["action"] == "TRIM"
    assert first_action["reasonCode"] == "SINGLE_NAME_CAP_BREACH"
    assert first_action["trimPlan"]["advisoryOnly"] is True
    assert packet["decisionReceipt"]["advisoryOnly"] is True
    assert packet["decisionReceipt"]["noOrderPlaced"] is True
    assert packet["decisionReceipt"]["sizingMath"]["estimatedSellValue"] > 22000
    assert any("META" in breach["message"] for breach in packet["portfolioRisk"]["singleNameBreaches"])
    assert packet["recommendedPriority"]["blockedActions"]


def test_ai_model_router_defaults_and_updates_are_auditable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        defaults = client.get("/api/settings/ai/model-router")
        assert defaults.status_code == 200
        router = defaults.json()["model_router"]
        assert router["fast"]["model"] == "gpt-5.4-mini"
        assert router["leadPM"]["model"] == "gpt-5.5"
        assert router["leadPM"]["reasoningEffort"] == "medium"

        update = client.put(
            "/api/settings/ai/model-router",
            json={"mode": "balanced", "leadPM": {"model": "gpt-5.5", "reasoningEffort": "high", "maxOutputTokens": 3000}},
        )
        assert update.status_code == 200
        status = update.json()["ai_status"]

    assert status["model_router"]["leadPM"]["reasoningEffort"] == "high"
    assert "lead PM high" in status["profile_summary"]


def test_live_eval_endpoint_uses_decision_and_copilot_with_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import decision_service, copilot_service

    def decision_response(payload, api_key):
        context = json.loads(payload["input"])
        return {
            "id": "decision",
            "output_text": json.dumps(
                {
                    "portfolio_verdict": "Hold current positions and stagger only eligible adds.",
                    "holding_decisions": context["deterministic_decision"]["holding_decisions"],
                    "opportunity_decisions": context["deterministic_decision"]["opportunity_decisions"][:2],
                    "execution_plan": ["Hold, then stagger entries."],
                    "staggering_guidance": ["Use tranches."],
                    "entry_conditions": ["Fresh data."],
                    "risks": ["Risk and data freshness matter."],
                    "data_used": ["quant tools", "risk gates"],
                    "missing_data": [],
                    "what_would_change_my_mind": ["Weakening momentum."],
                }
            ),
            "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
        }

    def copilot_response(payload, api_key):
        return {
            "id": "copilot",
            "output_text": json.dumps(
                {
                    "answer": "The quant risk tools say hold, stagger eligible adds, and respect data freshness.",
                    "data_used": ["latest advisor decision"],
                    "limitations": ["No invented prices."],
                    "suggested_followups": ["What should I trim?"],
                }
            ),
            "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        }

    monkeypatch.setattr(decision_service, "_call_openai_response", decision_response)
    monkeypatch.setattr(copilot_service, "_call_openai_response", copilot_response)

    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/evals/advisor-live")

    assert response.status_code == 200
    result = response.json()["eval"]
    assert result["status"] in {"pass", "review"}
    assert result["total_tokens"] == 70
    assert result["rubric"]["records_tokens"] is True
