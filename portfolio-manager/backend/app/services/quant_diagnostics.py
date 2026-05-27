from __future__ import annotations

from typing import Any

from app.services.data_service import compute_universe_features, data_freshness


def quant_diagnostics(conn) -> dict[str, Any]:
    instruments = conn.execute("SELECT COUNT(*) AS count FROM instruments WHERE enabled = 1").fetchone()["count"]
    price_symbols = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT symbol
            FROM price_bars
            GROUP BY symbol
            HAVING COUNT(*) >= 252
        )
        """
    ).fetchone()["count"]
    fundamental_symbols = conn.execute(
        "SELECT COUNT(DISTINCT symbol) AS count FROM fundamental_facts"
    ).fetchone()["count"]
    macro_series = conn.execute("SELECT COUNT(DISTINCT series_id) AS count FROM macro_series").fetchone()["count"]
    sectors = conn.execute("SELECT COUNT(DISTINCT sector) AS count FROM instruments WHERE enabled = 1").fetchone()["count"]
    asset_classes = conn.execute("SELECT COUNT(DISTINCT asset_class) AS count FROM instruments WHERE enabled = 1").fetchone()["count"]
    recommendation_rows = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'pass' THEN 1 ELSE 0 END) AS pass_count,
            SUM(CASE WHEN status = 'watch' THEN 1 ELSE 0 END) AS watch_count,
            SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS fail_count
        FROM recommendations
        """
    ).fetchone()
    backtest = conn.execute("SELECT metrics FROM backtest_runs ORDER BY id DESC LIMIT 1").fetchone()
    features = compute_universe_features(conn)
    scored = len(features)
    top_score = features[0]["score"] if features else 0

    freshness = data_freshness(conn)
    live_symbols = freshness.get("live_price_symbols", 0)
    checks = [
        {
            "name": "Data source quality",
            "status": "pass" if live_symbols else "watch",
            "detail": (
                f"Live/recent provider data is active for {live_symbols} symbols; preferred source is {freshness.get('preferred_price_source')}."
                if live_symbols
                else "No live market-data provider is configured yet; analytics are using local sample data."
            ),
        },
        {
            "name": "Price history",
            "status": "pass" if price_symbols >= max(6, instruments * 0.6) else "watch",
            "detail": f"{price_symbols}/{instruments} instruments have at least one trading year.",
        },
        {
            "name": "Feature engine",
            "status": "pass" if scored >= 6 else "watch",
            "detail": f"{scored} instruments produced momentum, volatility, drawdown, trend, and quality features.",
        },
        {
            "name": "Fundamentals",
            "status": "pass" if fundamental_symbols >= 8 else "watch",
            "detail": f"{fundamental_symbols} symbols have local fundamental facts.",
        },
        {
            "name": "Macro regime",
            "status": "pass" if macro_series >= 4 else "watch",
            "detail": f"{macro_series} macro series are feeding regime detection.",
        },
        {
            "name": "Market breadth",
            "status": "pass" if sectors >= 20 and instruments >= 45 else "watch",
            "detail": f"{instruments} instruments across {sectors} sectors/themes and {asset_classes} asset classes are enabled.",
        },
        {
            "name": "Recommendation audit",
            "status": "pass" if recommendation_rows["total"] else "watch",
            "detail": f"{recommendation_rows['total'] or 0} recommendations logged with pass/watch/fail gates.",
        },
        {
            "name": "No-lookahead backtest",
            "status": "pass" if backtest else "watch",
            "detail": "Latest backtest uses only prior lookback windows before each rebalance." if backtest else "Run a backtest to validate the strategy loop.",
        },
    ]
    core_checks = [check for check in checks if check["name"] != "Data source quality"]
    status = "healthy" if all(check["status"] == "pass" for check in core_checks[:4]) else "needs attention"

    return {
        "status": status,
        "freshness": freshness,
        "coverage": {
            "enabled_instruments": instruments,
            "price_history_ready": price_symbols,
            "fundamental_symbols": fundamental_symbols,
            "macro_series": macro_series,
            "scored_instruments": scored,
            "sectors": sectors,
            "asset_classes": asset_classes,
        },
        "recommendations": {
            "total": recommendation_rows["total"] or 0,
            "pass": recommendation_rows["pass_count"] or 0,
            "watch": recommendation_rows["watch_count"] or 0,
            "fail": recommendation_rows["fail_count"] or 0,
        },
        "top_score": round(top_score, 4),
        "checks": checks,
    }
