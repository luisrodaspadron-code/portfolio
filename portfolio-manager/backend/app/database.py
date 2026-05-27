from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings


DEFAULT_RISK_RULES: dict[str, Any] = {
    "max_single_stock_weight": 0.08,
    "max_etf_weight": 0.25,
    "max_sector_weight": 0.30,
    "max_crypto_weight": 0.05,
    "drawdown_warning": 0.12,
    "emergency_risk_off": 0.20,
    "min_liquidity_score": 65,
    "max_positions": 18,
    "base_currency": "USD",
    "real_money_trading_enabled": False,
    "decision_cadence": "daily_weekly",
    "autopilot_enabled": True,
    "autopilot_interval_hours": 24,
    "policy_objective": "competition_growth",
    "policy_risk": "aggressive_managed",
    "policy_diversification": "broad_opportunistic",
}


def dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_db_path() -> Path:
    return get_settings().resolved_database_path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                sector TEXT NOT NULL,
                is_multi_asset INTEGER NOT NULL DEFAULT 0,
                liquidity_score REAL NOT NULL DEFAULT 75,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS price_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                source TEXT NOT NULL,
                UNIQUE(symbol, date, source),
                FOREIGN KEY(symbol) REFERENCES instruments(symbol)
            );

            CREATE TABLE IF NOT EXISTS fundamental_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                metric TEXT NOT NULL,
                period TEXT NOT NULL,
                value REAL NOT NULL,
                source TEXT NOT NULL,
                UNIQUE(symbol, metric, period, source),
                FOREIGN KEY(symbol) REFERENCES instruments(symbol)
            );

            CREATE TABLE IF NOT EXISTS macro_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id TEXT NOT NULL,
                date TEXT NOT NULL,
                value REAL NOT NULL,
                source TEXT NOT NULL,
                UNIQUE(series_id, date, source)
            );

            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mode TEXT NOT NULL,
                base_currency TEXT NOT NULL DEFAULT 'USD',
                cash REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                UNIQUE(portfolio_id, symbol),
                FOREIGN KEY(portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY(symbol) REFERENCES instruments(symbol)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY(symbol) REFERENCES instruments(symbol)
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                target_weight REAL NOT NULL,
                confidence REAL NOT NULL,
                expected_return REAL NOT NULL,
                risk_score REAL NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                source_data_age_days INTEGER NOT NULL,
                portfolio_impact TEXT NOT NULL,
                risk_flags TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(symbol) REFERENCES instruments(symbol)
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                params TEXT NOT NULL,
                metrics TEXT NOT NULL,
                equity_curve TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS research_memos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_id INTEGER,
                symbol TEXT NOT NULL,
                title TEXT NOT NULL,
                thesis TEXT NOT NULL,
                evidence TEXT NOT NULL,
                risks TEXT NOT NULL,
                counterargument TEXT NOT NULL,
                change_mind TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(recommendation_id) REFERENCES recommendations(id),
                FOREIGN KEY(symbol) REFERENCES instruments(symbol)
            );

            CREATE TABLE IF NOT EXISTS ai_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                purpose TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                response_id TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS risk_rules (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS local_secrets (
                provider TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(provider, key)
            );

            CREATE TABLE IF NOT EXISTS connection_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                tested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                records INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS decision_packets (
                packet_hash TEXT PRIMARY KEY,
                packet TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS advisor_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                brief TEXT NOT NULL,
                highest_priority_action TEXT NOT NULL DEFAULT '{}',
                approved_actions TEXT NOT NULL DEFAULT '[]',
                concerns TEXT NOT NULL DEFAULT '[]',
                rejected_or_blocked_ideas TEXT NOT NULL DEFAULT '[]',
                missing_data TEXT NOT NULL DEFAULT '[]',
                what_would_change_my_mind TEXT NOT NULL DEFAULT '[]',
                fallback_reason TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                response_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(packet_hash) REFERENCES decision_packets(packet_hash)
            );

            CREATE TABLE IF NOT EXISTS advisor_review_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                quant_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'ai',
                FOREIGN KEY(review_id) REFERENCES advisor_reviews(id)
            );

            CREATE TABLE IF NOT EXISTS automation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                summary TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS automation_run_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                records INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                technical_detail TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(run_id) REFERENCES automation_runs(id)
            );

            CREATE TABLE IF NOT EXISTS provider_refreshes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                records INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS universe_assets (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_class TEXT NOT NULL DEFAULT 'Stock',
                exchange TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                tradable INTEGER NOT NULL DEFAULT 0,
                marginable INTEGER NOT NULL DEFAULT 0,
                shortable INTEGER NOT NULL DEFAULT 0,
                fractionable INTEGER NOT NULL DEFAULT 0,
                attributes TEXT NOT NULL DEFAULT '[]',
                is_ipo INTEGER NOT NULL DEFAULT 0,
                cik TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'sample',
                included INTEGER NOT NULL DEFAULT 1,
                exclusion_reason TEXT NOT NULL DEFAULT '',
                liquidity_tier TEXT NOT NULL DEFAULT 'unknown',
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS factor_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                source TEXT NOT NULL,
                factors TEXT NOT NULL,
                score REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, snapshot_date, source)
            );

            CREATE TABLE IF NOT EXISTS decision_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                portfolio_verdict TEXT NOT NULL,
                execution_plan TEXT NOT NULL DEFAULT '[]',
                staggering_guidance TEXT NOT NULL DEFAULT '[]',
                entry_conditions TEXT NOT NULL DEFAULT '[]',
                risks TEXT NOT NULL DEFAULT '[]',
                data_used TEXT NOT NULL DEFAULT '[]',
                missing_data TEXT NOT NULL DEFAULT '[]',
                what_would_change_my_mind TEXT NOT NULL DEFAULT '[]',
                fallback_reason TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                response_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS decision_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_run_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                item_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                plain_action TEXT NOT NULL,
                reason TEXT NOT NULL,
                target_weight REAL NOT NULL DEFAULT 0,
                current_weight REAL NOT NULL DEFAULT 0,
                confidence_label TEXT NOT NULL DEFAULT '',
                confidence_score REAL NOT NULL DEFAULT 0,
                eligibility TEXT NOT NULL DEFAULT '',
                risk_check TEXT NOT NULL DEFAULT '',
                quant_evidence TEXT NOT NULL DEFAULT '[]',
                ai_commentary TEXT NOT NULL DEFAULT '',
                source_freshness TEXT NOT NULL DEFAULT '',
                reason_code TEXT NOT NULL DEFAULT '',
                detail_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(decision_run_id) REFERENCES decision_runs(id)
            );

            CREATE TABLE IF NOT EXISTS advisor_eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                model TEXT NOT NULL,
                decision_run_id INTEGER,
                rubric TEXT NOT NULL DEFAULT '{}',
                questions TEXT NOT NULL DEFAULT '[]',
                total_tokens INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS provider_rate_limits (
                provider TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'ok',
                reset_at TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _ensure_column(conn, "research_memos", "generation_method", "generation_method TEXT NOT NULL DEFAULT 'rules_based'")
        _ensure_column(conn, "research_memos", "ai_provider", "ai_provider TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "research_memos", "ai_model", "ai_model TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "research_memos", "input_tokens", "input_tokens INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "research_memos", "output_tokens", "output_tokens INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "research_memos", "total_tokens", "total_tokens INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "decision_items", "reason_code", "reason_code TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "decision_items", "detail_payload", "detail_payload TEXT NOT NULL DEFAULT '{}'")

        for key, value in DEFAULT_RISK_RULES.items():
            conn.execute(
                "INSERT OR IGNORE INTO risk_rules (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )

        existing = conn.execute("SELECT id FROM portfolios WHERE mode = 'paper' LIMIT 1").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO portfolios (name, mode, base_currency, cash) VALUES (?, ?, ?, ?)",
                ("Competition Paper Portfolio", "paper", "USD", 100000.0),
            )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def get_risk_rules(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM risk_rules").fetchall()
    rules: dict[str, Any] = {}
    for row in rows:
        try:
            rules[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError:
            rules[row["key"]] = row["value"]
    return {**DEFAULT_RISK_RULES, **rules}


def get_app_settings(conn: sqlite3.Connection, prefix: str = "") -> dict[str, Any]:
    if prefix:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE ?", (f"{prefix}%",)).fetchall()
    else:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    settings: dict[str, Any] = {}
    for row in rows:
        try:
            settings[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError:
            settings[row["key"]] = row["value"]
    return settings


def update_app_settings(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    for key, value in values.items():
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, json.dumps(value)),
        )
    return get_app_settings(conn)


def update_risk_rules(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DEFAULT_RISK_RULES)
    for key, value in values.items():
        if key not in allowed:
            continue
        conn.execute(
            """
            INSERT INTO risk_rules (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, json.dumps(value)),
        )
    return get_risk_rules(conn)
