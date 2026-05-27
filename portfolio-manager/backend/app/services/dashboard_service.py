from __future__ import annotations

from app.database import get_risk_rules
from app.providers.registry import provider_statuses
from app.scheduler import scheduler
from app.services.action_service import portfolio_action_items
from app.services.advisor_packet import build_canonical_advisor_packet
from app.services.advisor_intelligence import advisor_trace_from_packet, build_advisor_packet, decision_packet_status, latest_advisor_review
from app.services.advisor_service import advisor_status, latest_advisor_run_detail
from app.services.ai_service import ai_status
from app.services.analytics import correlation_matrix
from app.services.backtest_service import recent_backtests
from app.services.data_service import compute_universe_features, data_freshness, load_price_series
from app.services.connections_service import connections_status
from app.services.decision_service import latest_decision, latest_eval
from app.services.portfolio_service import portfolio_summary
from app.services.policy_service import policy_status
from app.services.quant_diagnostics import quant_diagnostics
from app.services.recommendation_service import latest_macro, recent_recommendations, research_memos
from app.services.strategy_service import market_scope, strategy_reviews
from app.services.trend_service import portfolio_trend
from app.services.universe_service import universe_status


def dashboard(conn) -> dict:
    paper = portfolio_summary(conn, mode="paper")
    real_rows = conn.execute("SELECT id FROM portfolios WHERE mode IN ('real', 'watchlist') ORDER BY mode = 'real' DESC, id LIMIT 1").fetchone()
    real = portfolio_summary(conn, real_rows["id"], "real") if real_rows else None
    features = compute_universe_features(conn)
    strategies = strategy_reviews(features)
    top_symbols = [item["symbol"] for item in features[:8]]
    series = load_price_series(conn, top_symbols)
    close_series = {symbol: [point["close"] for point in points] for symbol, points in series.items()}
    recommendations = recent_recommendations(conn, 10)
    diagnostics = quant_diagnostics(conn)
    freshness = data_freshness(conn)
    macro = latest_macro(conn)
    packet = build_advisor_packet(conn)
    canonical_packet = build_canonical_advisor_packet(conn, next_review_at=scheduler.status().get("next_run_at"))
    advisor_trace = advisor_trace_from_packet(conn, packet)
    trend = portfolio_trend(conn, mode="real")
    latest_run = latest_advisor_run_detail(conn)
    decision = latest_decision(conn)
    primary_plan = (decision or {}).get("execution_plan", [])[:4] if decision else []
    what_changed = {
        "risk": real["stress"]["warnings"][0] if real and real["stress"]["warnings"] else "No hard risk breach in the current packet.",
        "data": (freshness.get("latest_provider_refresh") or {}).get("message", "No provider refresh has run yet."),
        "ai": (decision or {}).get("fallback_reason") or ((decision or {}).get("status", "waiting")),
    }
    return {
        "paper_portfolio": paper,
        "real_portfolio": real,
        "watchlist_portfolio": real,
        "portfolio_trend": trend,
        "opportunities": features[:12],
        "macro_regime": macro,
        "recent_recommendations": recommendations,
        "research_memos": research_memos(conn, 6),
        "recent_backtests": recent_backtests(conn, 3),
        "correlations": correlation_matrix(close_series) if close_series else {},
        "risk_rules": get_risk_rules(conn),
        "data_freshness": freshness,
        "providers": provider_statuses(conn),
        "scheduler": scheduler.status(),
        "connections": connections_status(conn),
        "quant_diagnostics": diagnostics,
        "advisor": advisor_status(conn),
        "advisor_review": latest_advisor_review(conn),
        "advisor_decision": decision,
        "advisor_run_status": latest_run,
        "advisor_eval": latest_eval(conn),
        "advisor_packet": canonical_packet,
        "advisor_trace": advisor_trace,
        "ai_activity": advisor_trace["ai_activity"],
        "decision_packet_status": decision_packet_status(packet),
        "portfolio_pulse": {
            "current_value": real["total_value"] if real else 0,
            "positions": len(real["positions"]) if real else 0,
            "day_change": trend["day_change"],
            "day_change_pct": trend["day_change_pct"],
            "trend_available": len(trend["points"]) >= 2,
            "source_note": trend["source_note"],
        },
        "what_changed": what_changed,
        "primary_execution_plan": primary_plan,
        "compact_system_status": {
            "portfolio": "Imported" if real and real["positions"] else "Missing",
            "ai": advisor_trace["ai_activity"],
            "risk": "Review" if real and real["stress"]["warnings"] else "Clear",
            "data": advisor_trace["provider_freshness"]["mode"],
        },
        "action_items": portfolio_action_items(
            real_portfolio=real,
            recommendations=recommendations,
            diagnostics=diagnostics,
            macro=macro,
            strategies=strategies,
        ),
        "market_scope": market_scope(conn),
        "universe_status": universe_status(conn),
        "strategy_reviews": strategies,
        "policy": policy_status(conn),
        "ai_status": ai_status(conn),
    }
