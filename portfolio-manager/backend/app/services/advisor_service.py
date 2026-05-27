from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from app.database import get_conn
from app.models import BacktestRequest, RecommendationRunRequest
from app.services.backtest_service import run_backtest
from app.services.ai_service import ai_runtime_settings
from app.services.data_service import data_freshness, refresh_data
from app.services.decision_service import run_advisor_decision
from app.services.portfolio_service import portfolio_summary
from app.services.quant_diagnostics import quant_diagnostics
from app.services.recommendation_service import run_recommendations
from app.services.strategy_service import strategy_reviews
from app.services.data_service import compute_universe_features
from app.services.universe_service import refresh_universe
from app.services import run_events


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _receipt(step: str, status: str, *, records: int = 0, message: str = "", technical_detail: str = "", started_at: str | None = None) -> dict[str, Any]:
    return {
        "step": step,
        "status": status,
        "records": records,
        "started_at": started_at or _now(),
        "finished_at": _now(),
        "message": message,
        "technical_detail": technical_detail,
    }


def _event_phase(step: str) -> str:
    text = step.lower()
    if "universe" in text:
        return "universe"
    if "price" in text or "provider" in text:
        return "prices"
    if "portfolio" in text:
        return "holdings"
    if "factor" in text:
        return "factors"
    if "backtest" in text:
        return "candidates"
    if "risk" in text or "gate" in text:
        return "risk"
    if "ai" in text:
        return "llm"
    if "decision" in text or "summary" in text:
        return "receipt"
    if "stopped" in text:
        return "error"
    return "complete"


def _event_status(status: str) -> str:
    if status == "running":
        return "running"
    if status in {"failed", "error"}:
        return "error"
    if status in {"warning", "skipped", "partial"}:
        return "warning"
    return "success"


def _run_events(steps: list[dict[str, Any]], run_id: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for step in steps:
        metrics: dict[str, str | int | float] = {}
        if step.get("records"):
            metrics["records"] = int(step.get("records") or 0)
        events.append(
            {
                "runId": str(run_id),
                "timestamp": step.get("finished_at") or step.get("started_at") or _now(),
                "phase": _event_phase(str(step.get("step") or "")),
                "status": _event_status(str(step.get("status") or "")),
                "title": step.get("step") or "Advisor event",
                "detail": step.get("message") or "",
                "metrics": metrics,
                "source": step.get("technical_detail") or "",
            }
        )
    return events


def _safe_cycle_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "429" in message or "rate limit" in lowered or "too many requests" in lowered:
        return "OpenAI is rate-limiting this key right now. Quant-only fallback is active."
    if "database is locked" in lowered or "database locked" in lowered:
        return "The local database was busy finishing another advisor task. Wait a few seconds and run the cycle again."
    if "timeout" in lowered or "timed out" in lowered:
        return "A provider took too long to respond. Signal PM kept the last valid packet and will retry on the next run."
    if "openai" in lowered or "api.openai.com" in lowered or "httpx" in lowered:
        return "The AI provider request failed. Signal PM kept the quant decision path active."
    return "Advisor cycle could not finish. Signal PM kept the last valid dashboard and run receipt."


def _insert_run(conn, trigger: str, status: str, started_at: str, summary: dict[str, Any], error: str = "") -> int:
    cursor = conn.execute(
        """
        INSERT INTO automation_runs (trigger, status, started_at, finished_at, summary, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (trigger, status, started_at, "" if status == "running" else _now(), json.dumps(summary), error),
    )
    return int(cursor.lastrowid)


def _create_run(trigger: str) -> dict[str, Any]:
    started_at = _now()
    with get_conn() as conn:
        run_id = _insert_run(conn, trigger, "running", started_at, {}, "")
    run_events.publish(
        run_id,
        type="run",
        phase="lifecycle",
        status="running",
        title="Advisor run started",
        detail=f"Trigger: {trigger}.",
        metrics={"trigger": trigger},
    )
    return {"id": run_id, "status": "running", "started_at": started_at}


def _update_run(run_id: int, status: str, started_at: str, summary: dict[str, Any], error: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE automation_runs
            SET status = ?, finished_at = ?, summary = ?, error = ?
            WHERE id = ?
            """,
            (status, _now(), json.dumps(summary), error, run_id),
        )
    run_events.publish(
        run_id,
        type="run",
        phase="lifecycle",
        status=status,
        title="Advisor run finished" if status == "success" else "Advisor run stopped",
        detail=error or f"Status: {status}.",
        metrics={
            "status": status,
            "records_processed": sum(
                int(receipt.get("records") or 0)
                for receipt in summary.get("step_receipts", [])
                if isinstance(receipt, dict)
            ),
        },
    )


def _begin_step(run_id: int | None, step: str, message: str = "") -> int | None:
    if run_id is None:
        return None
    try:
        with get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO automation_run_steps
                (run_id, step, status, records, started_at, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, step, "running", 0, _now(), message),
            )
            step_id = int(cursor.lastrowid)
    except (sqlite3.OperationalError, sqlite3.IntegrityError):
        return None
    run_events.publish(
        run_id,
        type="step",
        phase=_event_phase(step),
        status="running",
        title=step,
        detail=message,
        metrics={"stepId": step_id},
    )
    return step_id


def _finish_step(step_id: int | None, receipt: dict[str, Any]) -> None:
    if step_id is None:
        return
    try:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE automation_run_steps
                SET status = ?, records = ?, finished_at = ?, message = ?, technical_detail = ?
                WHERE id = ?
                """,
                (
                    receipt["status"],
                    int(receipt.get("records") or 0),
                    receipt["finished_at"],
                    receipt.get("message", ""),
                    receipt.get("technical_detail", ""),
                    step_id,
                ),
            )
            row = conn.execute("SELECT run_id FROM automation_run_steps WHERE id = ?", (step_id,)).fetchone()
    except (sqlite3.OperationalError, sqlite3.IntegrityError):
        return
    run_id = int(row["run_id"]) if row else None
    if run_id is not None:
        run_events.publish(
            run_id,
            type="step",
            phase=_event_phase(str(receipt.get("step") or "")),
            status=_event_status(str(receipt.get("status") or "")),
            title=str(receipt.get("step") or "Advisor step"),
            detail=str(receipt.get("message") or ""),
            metrics={
                "stepId": step_id,
                "records": int(receipt.get("records") or 0),
            },
            source=str(receipt.get("technical_detail") or ""),
        )


def _append_receipt(summary: dict[str, Any], receipt: dict[str, Any], step_id: int | None = None) -> None:
    summary["step_receipts"].append(receipt)
    _finish_step(step_id, receipt)


def advisor_run_detail(conn, run_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM automation_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise ValueError("Advisor run not found.")
    steps = conn.execute("SELECT * FROM automation_run_steps WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    summary = json.loads(row["summary"] or "{}")
    current = next((dict(step) for step in steps if step["status"] == "running"), None)
    completed = [dict(step) for step in steps if step["status"] != "running"]
    latest = dict(steps[-1]) if steps else None
    universe = summary.get("universe", {}) if isinstance(summary, dict) else {}
    data_counts = summary.get("data_counts", {}) if isinstance(summary, dict) else {}
    priced_symbols = data_counts.get("priced_symbols")
    if not priced_symbols:
        freshness = data_freshness(conn)
        priced_symbols = freshness.get("live_price_symbols") or freshness.get("sample_price_symbols") or 0
    provider_results = summary.get("provider_results", []) if isinstance(summary, dict) else []
    bus_events = run_events.history_as_dicts(int(row["id"]))
    step_events = _run_events([dict(step) for step in steps], int(row["id"]))
    events = bus_events if bus_events else step_events
    return {
        "run_id": row["id"],
        "status": row["status"],
        "trigger": row["trigger"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "current_step": current or latest,
        "completed_steps": completed,
        "steps": [dict(step) for step in steps],
        "events": events,
        "records_processed": sum(int(step["records"] or 0) for step in steps),
        "fallback_reason": row["error"] or summary.get("fallback_reason", ""),
        "model": summary.get("ai_model", ""),
        "reasoning": summary.get("ai_reasoning", ""),
        "token_usage": summary.get("ai_tokens", 0),
        "universe_size": universe.get("included_assets", 0),
        "priced_symbols": priced_symbols,
        "sec_used": any(item.get("provider") == "sec_edgar" and item.get("status") in {"success", "partial"} for item in provider_results),
        "fred_used": any(item.get("provider") == "fred" and item.get("status") in {"success", "partial"} for item in provider_results),
        "decision_hash": summary.get("decision_hash", ""),
        "summary": summary,
        "error": row["error"],
    }


def latest_advisor_run_detail(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT id FROM automation_runs ORDER BY id DESC LIMIT 1").fetchone()
    return advisor_run_detail(conn, int(row["id"])) if row else None


def advisor_status(conn) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM automation_runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {
            "enabled": True,
            "cadence": "daily",
            "last_run": None,
            "summary": {},
            "message": "Autopilot has not run yet.",
        }
    return {
        "enabled": True,
        "cadence": "daily",
        "last_run": {
            "id": row["id"],
            "trigger": row["trigger"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error": row["error"],
        },
        "summary": json.loads(row["summary"] or "{}"),
        "message": "Advisor autopilot is running the full quant cycle automatically.",
    }


def run_advisor_cycle(trigger: str = "manual", run_id: int | None = None) -> dict[str, Any]:
    if run_id is None:
        created = _create_run(trigger)
        run_id = int(created["id"])
        started_at = str(created["started_at"])
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT started_at FROM automation_runs WHERE id = ?", (run_id,)).fetchone()
        started_at = str(row["started_at"]) if row else _now()
    summary: dict[str, Any] = {
        "steps": [],
        "step_receipts": [],
        "recommendations": 0,
        "memos": 0,
        "backtest": None,
        "real_portfolio_loaded": False,
    }

    try:
        with get_conn() as conn:
            step_started = _now()
            step_id = _begin_step(run_id, "Universe screened", "Checking tradable universe and coverage.")
            universe = refresh_universe(conn)
            summary["steps"].append("universe_refresh")
            summary["universe"] = universe.get("universe", {})
            conn.commit()
            _append_receipt(
                summary,
                _receipt(
                    "Universe screened",
                    "updated" if universe.get("providers") else "reused",
                    records=int((universe.get("universe") or {}).get("included_assets") or 0),
                    message=f"{(universe.get('universe') or {}).get('scope_label', 'Market universe checked')}.",
                    technical_detail=json.dumps(universe.get("providers", [])),
                    started_at=step_started,
                ),
                step_id,
            )

        step_started = _now()
        step_id = _begin_step(run_id, "Prices checked", "Refreshing prices and provider freshness.")
        data_result = refresh_data(force_sample=False)
        summary["steps"].append("data_refresh")
        summary["data_counts"] = data_result.get("counts", {})
        if not summary["data_counts"].get("priced_symbols"):
            with get_conn() as conn:
                freshness = data_freshness(conn)
            summary["data_counts"]["priced_symbols"] = freshness.get("live_price_symbols") or freshness.get("sample_price_symbols") or 0
        summary["provider_results"] = data_result.get("providers", [])
        live_records = sum(int(item.get("records") or 0) for item in data_result.get("providers", []) if item.get("status") in {"success", "partial"})
        failed = [item for item in data_result.get("providers", []) if item.get("status") == "failed"]
        _append_receipt(
            summary,
            _receipt(
                "Prices checked",
                "warning" if failed else "updated" if live_records else "reused",
                records=live_records or int((data_result.get("counts") or {}).get("price_bars") or 0),
                message=data_result.get("message", "Price data checked."),
                technical_detail=json.dumps(data_result.get("providers", [])),
                started_at=step_started,
            ),
            step_id,
        )

        with get_conn() as conn:
            step_started = _now()
            step_id = _begin_step(run_id, "Portfolio loaded", "Loading current real-money holdings.")
            real = portfolio_summary(conn, mode="real")
            summary["real_portfolio_loaded"] = bool(real["positions"] or real["cash"] > 0)
            summary["real_portfolio_value"] = real["total_value"]
            summary["real_positions"] = len(real["positions"])
            _append_receipt(
                summary,
                _receipt(
                    "Portfolio loaded",
                    "updated" if summary["real_portfolio_loaded"] else "skipped",
                    records=len(real["positions"]),
                    message=f"{len(real['positions'])} holdings analyzed; total value ${real['total_value']:,.2f}.",
                    started_at=step_started,
                ),
                step_id,
            )

            step_started = _now()
            step_id = _begin_step(run_id, "Factors scored", "Scoring candidates across momentum, quality, risk, and freshness.")
            recommendations = run_recommendations(
                conn,
                RecommendationRunRequest(max_ideas=12, portfolio_id=real["id"], generate_ai_memos=False),
            )
            summary["steps"].append("recommendations")
            summary["recommendations"] = len(recommendations["recommendations"])
            summary["buy_ideas"] = sum(1 for item in recommendations["recommendations"] if item["action"] == "BUY")
            summary["watch_ideas"] = sum(1 for item in recommendations["recommendations"] if item["action"] == "WATCH")
            conn.commit()
            _append_receipt(
                summary,
                _receipt(
                    "Factors scored",
                    "updated",
                    records=len(recommendations["recommendations"]),
                    message="Momentum, quality, value proxy, drawdown, liquidity, and source freshness were scored.",
                    started_at=step_started,
                ),
                step_id,
            )

            step_started = _now()
            step_id = _begin_step(run_id, "Backtest context", "Refreshing deterministic walk-forward evidence.")
            try:
                backtest = run_backtest(conn, BacktestRequest())
                summary["steps"].append("backtest")
                summary["backtest"] = {
                    "id": backtest["id"],
                    "total_return": backtest["metrics"].get("total_return", 0),
                    "max_drawdown": backtest["metrics"].get("max_drawdown", 0),
                    "sharpe": backtest["metrics"].get("sharpe", 0),
                }
                conn.commit()
                _append_receipt(
                    summary,
                    _receipt(
                        "Backtest context",
                        "updated",
                        records=1,
                        message=f"Walk-forward evidence refreshed; max drawdown {backtest['metrics'].get('max_drawdown', 0):.1%}.",
                        started_at=step_started,
                    ),
                    step_id,
                )
            except ValueError as exc:
                summary["steps"].append("backtest_skipped")
                summary["backtest_error"] = str(exc)
                _append_receipt(
                    summary,
                    _receipt(
                        "Backtest context",
                        "skipped",
                        message="Backtest skipped because the current data set is not ready.",
                        technical_detail=str(exc),
                        started_at=step_started,
                    ),
                    step_id,
                )

            step_started = _now()
            step_id = _begin_step(run_id, "Risk gates applied", "Applying hard caps, diagnostics, and strategy sleeves.")
            diagnostics = quant_diagnostics(conn)
            summary["steps"].append("diagnostics")
            summary["diagnostics_status"] = diagnostics["status"]
            strategies = strategy_reviews(compute_universe_features(conn))
            summary["strategies_reviewed"] = len(strategies)
            summary["top_strategy"] = strategies[0]["name"] if strategies else None
            summary["memos"] = conn.execute("SELECT COUNT(*) AS count FROM research_memos").fetchone()["count"]
            conn.commit()
            _append_receipt(
                summary,
                _receipt(
                    "Risk gates applied",
                    "warning" if diagnostics["status"] != "healthy" else "updated",
                    records=int(diagnostics["recommendations"]["total"]),
                    message=f"Risk, coverage, and quant diagnostics are {diagnostics['status']}.",
                    technical_detail=json.dumps(diagnostics["checks"][:5]),
                    started_at=step_started,
                ),
                step_id,
            )

            step_started = _now()
            step_id = _begin_step(run_id, "AI review generated", "Sending the distilled quant packet to the portfolio advisor.")
            ai_settings = ai_runtime_settings(conn, "leadPM")
            decision = run_advisor_decision(conn, force=True)
            summary["steps"].append("advisor_decision")
            summary["advisor_decision_status"] = decision.get("status")
            summary["advisor_decision_id"] = decision.get("id")
            summary["advisor_verdict"] = decision.get("portfolio_verdict")
            summary["ai_model"] = decision.get("model")
            summary["ai_reasoning"] = ai_settings["reasoning_effort"]
            summary["ai_tokens"] = decision.get("total_tokens", 0)
            summary["decision_hash"] = decision.get("packet_hash")
            summary["fallback_reason"] = decision.get("fallback_reason", "")
            conn.commit()
            _append_receipt(
                summary,
                _receipt(
                    "AI review generated",
                    "updated" if decision.get("status") == "success" else "warning",
                    records=len(decision.get("holding_decisions", [])) + len(decision.get("opportunity_decisions", [])),
                    message=decision.get("fallback_reason") or f"{decision.get('model', 'AI')} produced the portfolio decision.",
                    technical_detail=decision.get("response_id", ""),
                    started_at=step_started,
                ),
                step_id,
            )
            step_started = _now()
            step_id = _begin_step(run_id, "Decision summary created", "Compiling the final action summary and receipt.")
            _append_receipt(
                summary,
                _receipt(
                    "Decision summary created",
                    "updated",
                    records=1,
                    message=decision.get("portfolio_verdict", "Decision summary created."),
                    started_at=step_started,
                ),
                step_id,
            )

            conn.commit()
            _update_run(run_id, "success", started_at, summary)
            return {"id": run_id, "run_id": run_id, "status": "success", "started_at": started_at, "finished_at": _now(), "summary": summary}
    except Exception as exc:
        safe_error = _safe_cycle_error(exc)
        step_id = _begin_step(run_id, "Advisor cycle stopped", safe_error)
        _append_receipt(
            summary,
            _receipt(
                "Advisor cycle stopped",
                "failed",
                message=safe_error,
                technical_detail=exc.__class__.__name__,
                started_at=started_at,
            ),
            step_id,
        )
        summary["fallback_reason"] = safe_error
        _update_run(run_id, "failed", started_at, summary, safe_error)
        return {"id": run_id, "run_id": run_id, "status": "failed", "started_at": started_at, "finished_at": _now(), "summary": summary, "error": safe_error}


def start_advisor_run(trigger: str = "manual") -> dict[str, Any]:
    created = _create_run(trigger)
    run_id = int(created["id"])
    thread = threading.Thread(target=run_advisor_cycle, kwargs={"trigger": trigger, "run_id": run_id}, daemon=True)
    thread.start()
    return {"run_id": run_id, "status": "running", "started_at": created["started_at"]}
