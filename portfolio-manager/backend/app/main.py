from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_conn, init_db, update_risk_rules
from app.models import (
    AiSettingsUpdate,
    AiModelConfigUpdate,
    BacktestRequest,
    ConnectionTestRequest,
    CopilotRequest,
    OpenAiKeyUpdate,
    PaperOrderRequest,
    PolicyUpdate,
    RecommendationRunRequest,
    RiskRulesUpdate,
    SecretUpdate,
)
from app.scheduler import scheduler
from app.services.advisor_packet import build_canonical_advisor_packet
from app.services.advisor_service import advisor_run_detail, advisor_status, run_advisor_cycle, start_advisor_run
from app.services.advisor_intelligence import (
    advisor_reviews,
    build_advisor_packet,
    build_advisor_trace,
    decision_packet_status,
    ensure_current_advisor_review,
    run_advisor_review,
    store_decision_packet,
)
from app.services.backtest_service import run_backtest
from app.services.dashboard_service import dashboard
from app.services.data_service import ensure_data, refresh_data
from app.services.ai_service import ai_model_config, apply_ai_settings, save_openai_key, test_openai_connection, update_ai_model_config
from app.services.connections_service import connections_status, delete_connection, save_connection, test_connection
from app.services.copilot_service import ask_copilot
from app.services.decision_service import latest_decision, run_advisor_decision, run_live_advisor_eval
from app.services.portfolio_service import execute_paper_order, import_holdings_csv
from app.services.policy_service import apply_policy
from app.services.quant_diagnostics import quant_diagnostics
from app.services.recommendation_service import research_memos, run_recommendations
from app.services.universe_service import refresh_universe, universe_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_data()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="Local Robo Portfolio Manager",
    version="0.1.0",
    description="Local-first portfolio research, paper trading, and decision support.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _try_auto_review(conn, trigger: str) -> dict:
    try:
        return ensure_current_advisor_review(conn, trigger=trigger)
    except Exception as exc:
        return {"ran": False, "trigger": trigger, "reason": f"Advisor auto-brief skipped: {exc}"}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "scheduler": scheduler.status()}


@app.get("/api/dashboard")
def get_dashboard() -> dict:
    with get_conn() as conn:
        return dashboard(conn)


@app.post("/api/import/holdings-csv")
async def import_holdings(file: UploadFile = File(...)) -> dict:
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    content = await file.read()
    try:
        with get_conn() as conn:
            result = import_holdings_csv(conn, content)
            result["advisor_auto_review"] = _try_auto_review(conn, "holdings_import")
            return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/data/refresh")
def refresh() -> dict:
    result = refresh_data(force_sample=False)
    with get_conn() as conn:
        result["advisor_auto_review"] = _try_auto_review(conn, "data_refresh")
    return result


@app.post("/api/universe/refresh")
def refresh_universe_endpoint() -> dict:
    with get_conn() as conn:
        return refresh_universe(conn)


@app.get("/api/universe/status")
def universe_status_endpoint() -> dict:
    with get_conn() as conn:
        return {"universe": universe_status(conn)}


@app.post("/api/backtests")
def create_backtest(payload: BacktestRequest) -> dict:
    try:
        with get_conn() as conn:
            return run_backtest(conn, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recommendations/run")
def create_recommendations(payload: RecommendationRunRequest) -> dict:
    with get_conn() as conn:
        return run_recommendations(conn, payload)


@app.post("/api/advisor/run")
def run_advisor_now() -> dict:
    return run_advisor_cycle(trigger="manual")


@app.post("/api/advisor/runs")
def start_advisor_now() -> dict:
    return start_advisor_run(trigger="manual")


@app.get("/api/advisor/runs/{run_id}")
def get_advisor_run(run_id: int) -> dict:
    try:
        with get_conn() as conn:
            return advisor_run_detail(conn, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/advisor/status")
def get_advisor_status() -> dict:
    with get_conn() as conn:
        return advisor_status(conn)


@app.get("/api/advisor/packet")
def get_advisor_packet() -> dict:
    with get_conn() as conn:
        packet = build_advisor_packet(conn)
        store_decision_packet(conn, packet)
        return {"packet": packet, "status": decision_packet_status(packet)}


@app.get("/api/advisor/packet/canonical")
def get_canonical_advisor_packet() -> dict:
    with get_conn() as conn:
        return {"advisor_packet": build_canonical_advisor_packet(conn, next_review_at=scheduler.status().get("next_run_at"))}


@app.get("/api/advisor/trace")
def get_advisor_trace() -> dict:
    with get_conn() as conn:
        return {"trace": build_advisor_trace(conn)}


@app.post("/api/advisor/review")
def post_advisor_review() -> dict:
    with get_conn() as conn:
        return {"advisor_review": run_advisor_review(conn)}


@app.get("/api/advisor/reviews")
def get_advisor_reviews() -> dict:
    with get_conn() as conn:
        return {"reviews": advisor_reviews(conn, 20)}


@app.post("/api/advisor/decision")
def post_advisor_decision() -> dict:
    with get_conn() as conn:
        return {"advisor_decision": run_advisor_decision(conn, force=True)}


@app.get("/api/advisor/decision/latest")
def get_latest_advisor_decision() -> dict:
    with get_conn() as conn:
        return {"advisor_decision": latest_decision(conn)}


@app.post("/api/evals/advisor-live")
def post_live_advisor_eval() -> dict:
    try:
        with get_conn() as conn:
            return {"eval": run_live_advisor_eval(conn)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ai/copilot")
def post_ai_copilot(payload: CopilotRequest) -> dict:
    with get_conn() as conn:
        return ask_copilot(conn, payload.question, payload.conversation_id, payload.screen_context)


@app.post("/api/portfolio/paper-order")
def paper_order(payload: PaperOrderRequest) -> dict:
    try:
        with get_conn() as conn:
            return execute_paper_order(conn, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/research/memos")
def get_memos() -> dict:
    with get_conn() as conn:
        return {"memos": research_memos(conn, 30)}


@app.get("/api/quant/diagnostics")
def get_quant_diagnostics() -> dict:
    with get_conn() as conn:
        return quant_diagnostics(conn)


@app.put("/api/settings/risk-rules")
def put_risk_rules(payload: RiskRulesUpdate) -> dict:
    with get_conn() as conn:
        return {"risk_rules": update_risk_rules(conn, payload.compact())}


@app.put("/api/settings/policy")
def put_policy(payload: PolicyUpdate) -> dict:
    try:
        with get_conn() as conn:
            return {"policy": apply_policy(conn, payload.objective, payload.risk, payload.diversification)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/settings/ai")
def put_ai_settings(payload: AiSettingsUpdate) -> dict:
    try:
        with get_conn() as conn:
            return {"ai_status": apply_ai_settings(conn, payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings/ai/model-router")
def get_ai_model_router() -> dict:
    with get_conn() as conn:
        return {"model_router": ai_model_config(conn)}


@app.put("/api/settings/ai/model-router")
def put_ai_model_router(payload: AiModelConfigUpdate) -> dict:
    try:
        with get_conn() as conn:
            return {"ai_status": update_ai_model_config(conn, payload.compact())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings/connections")
def get_connections() -> dict:
    with get_conn() as conn:
        return connections_status(conn)


@app.put("/api/settings/secrets")
def put_secret(payload: SecretUpdate) -> dict:
    try:
        with get_conn() as conn:
            return {"connections": save_connection(conn, payload.provider, payload.values)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/connections/test")
def post_connection_test(payload: ConnectionTestRequest) -> dict:
    try:
        with get_conn() as conn:
            result = test_connection(conn, payload.provider)
            if result.get("status") == "success":
                result["advisor_auto_review"] = _try_auto_review(conn, f"{payload.provider}_connection_test")
            return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/settings/secrets/{provider}")
def delete_secret(provider: str) -> dict:
    try:
        with get_conn() as conn:
            return {"connections": delete_connection(conn, provider)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/settings/openai-key")
def put_openai_key(payload: OpenAiKeyUpdate) -> dict:
    try:
        with get_conn() as conn:
            return {"ai_status": save_openai_key(conn, payload.api_key)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/ai/test")
def post_ai_connection_test() -> dict:
    try:
        with get_conn() as conn:
            ai_result = test_openai_connection(conn)
            response = {"ai_status": ai_result}
            if ai_result.get("state") == "live":
                response["advisor_auto_review"] = _try_auto_review(conn, "openai_connection_test")
            return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
