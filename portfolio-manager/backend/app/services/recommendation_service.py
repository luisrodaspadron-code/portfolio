from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.database import get_risk_rules
from app.services.ai_service import generate_research_memo
from app.services.data_service import compute_universe_features
from app.services.research import make_rules_based_memo
from app.services.risk import evaluate_candidate, target_weight_for_candidate


def latest_macro(conn) -> dict[str, Any]:
    from app.services.analytics import macro_regime

    rows = conn.execute("SELECT * FROM macro_series ORDER BY date").fetchall()
    return macro_regime(rows)


def run_recommendations(conn, payload) -> dict[str, Any]:
    rules = get_risk_rules(conn)
    universe = [item.upper() for item in payload.universe] if payload.universe else None
    features = compute_universe_features(conn, universe, store_snapshots=True)
    macro = latest_macro(conn)
    ideas: list[dict[str, Any]] = []
    for candidate in features[: max(payload.max_ideas * 2, 10)]:
        target_weight = target_weight_for_candidate(candidate, rules)
        status, flags = evaluate_candidate(candidate, target_weight, rules)
        action = "BUY" if status == "pass" and candidate["score"] > 0.04 else "WATCH" if status != "fail" else "AVOID"
        if candidate["score"] < -0.02:
            action = "TRIM"
        source_age = int(candidate.get("source_data_age_days", 0))
        source_name = candidate.get("price_source", "unknown")
        reason = (
            f"Score {candidate['score']:.2f}; confidence {candidate['confidence']:.0%}; "
            f"macro regime {macro['label']}; price source {source_name}, age {source_age}d."
        )
        impact = {
            "target_weight": target_weight,
            "expected_return": candidate["expected_return"],
            "risk_score": candidate["risk_score"],
            "sector": candidate["sector"],
            "price_source": source_name,
            "data_confidence": "sample_only" if source_name == "sample" else "stale" if source_age > 7 else "fresh",
        }
        cursor = conn.execute(
            """
            INSERT INTO recommendations
            (symbol, action, target_weight, confidence, expected_return, risk_score, status, reason,
             source_data_age_days, portfolio_impact, risk_flags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate["symbol"],
                action,
                target_weight,
                candidate["confidence"],
                candidate["expected_return"],
                candidate["risk_score"],
                status,
                reason,
                source_age,
                json.dumps(impact),
                json.dumps(flags),
            ),
        )
        recommendation = {
            "id": cursor.lastrowid,
            "symbol": candidate["symbol"],
            "name": candidate["name"],
            "action": action,
            "target_weight": target_weight,
            "confidence": candidate["confidence"],
            "expected_return": candidate["expected_return"],
            "risk_score": candidate["risk_score"],
            "status": status,
            "reason": reason,
            "source_data_age_days": source_age,
            "portfolio_impact": impact,
            "risk_flags": flags,
            "created_at": date.today().isoformat(),
        }
        memo = generate_research_memo(conn, candidate, recommendation, macro) if payload.generate_ai_memos else make_rules_based_memo(candidate, recommendation, macro)
        conn.execute(
            """
            INSERT INTO research_memos
            (recommendation_id, symbol, title, thesis, evidence, risks, counterargument, change_mind,
             generation_method, ai_provider, ai_model, input_tokens, output_tokens, total_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cursor.lastrowid,
                memo["symbol"],
                memo["title"],
                memo["thesis"],
                memo["evidence"],
                memo["risks"],
                memo["counterargument"],
                memo["change_mind"],
                memo["generation_method"],
                memo["ai_provider"],
                memo["ai_model"],
                memo["input_tokens"],
                memo["output_tokens"],
                memo["total_tokens"],
            ),
        )
        ai_run = memo.get("ai_run")
        if ai_run:
            conn.execute(
                """
                INSERT INTO ai_runs
                (provider, model, purpose, status, started_at, finished_at,
                 input_tokens, output_tokens, total_tokens, response_id, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ai_run["provider"],
                    ai_run["model"],
                    ai_run["purpose"],
                    ai_run["status"],
                    ai_run["started_at"],
                    ai_run["finished_at"],
                    ai_run["input_tokens"],
                    ai_run["output_tokens"],
                    ai_run["total_tokens"],
                    ai_run["response_id"],
                    ai_run["error"],
                ),
            )
        ideas.append(recommendation)
        if len(ideas) >= payload.max_ideas:
            break
    return {"macro_regime": macro, "recommendations": ideas, "risk_rules": rules}


def recent_recommendations(conn, limit: int = 8) -> list[dict[str, Any]]:
    latest_review = conn.execute("SELECT id FROM advisor_reviews ORDER BY id DESC LIMIT 1").fetchone()
    review_items: dict[str, dict[str, Any]] = {}
    if latest_review:
        rows = conn.execute(
            """
            SELECT symbol, action, status, quant_status, reason, source
            FROM advisor_review_items
            WHERE review_id = ?
            """,
            (latest_review["id"],),
        ).fetchall()
        review_items = {row["symbol"]: dict(row) for row in rows}
    rows = conn.execute(
        """
        SELECT r.*, i.name, i.asset_class, i.sector
        FROM recommendations r
        JOIN instruments i ON r.symbol = i.symbol
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["portfolio_impact"] = json.loads(item["portfolio_impact"])
        item["risk_flags"] = json.loads(item["risk_flags"])
        source = str(item["portfolio_impact"].get("price_source") or "unknown")
        if source == "sample":
            item["data_confidence"] = "sample_only"
        elif int(item.get("source_data_age_days") or 0) > 7:
            item["data_confidence"] = "stale"
        else:
            item["data_confidence"] = "fresh"
        item["ai_review"] = review_items.get(item["symbol"])
        items.append(item)
    return items


def research_memos(conn, limit: int = 20) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT rm.*, i.name, i.asset_class, i.sector
        FROM research_memos rm
        JOIN instruments i ON rm.symbol = i.symbol
        ORDER BY rm.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
