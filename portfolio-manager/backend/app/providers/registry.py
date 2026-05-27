from __future__ import annotations

from app.providers.alpaca import AlpacaProvider
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.fred import FredProvider
from app.providers.sec_edgar import SecEdgarProvider
from app.services.secrets_service import effective_settings


def _latest_provider_runs(conn) -> dict[str, dict]:
    if conn is None:
        return {}
    rows = conn.execute(
        """
        SELECT pr.*
        FROM provider_refreshes pr
        JOIN (
            SELECT provider, MAX(id) AS id
            FROM provider_refreshes
            GROUP BY provider
        ) latest ON pr.provider = latest.provider AND pr.id = latest.id
        """
    ).fetchall()
    return {row["provider"]: dict(row) for row in rows}


def provider_statuses(conn=None) -> list[dict]:
    if conn is None:
        from app.config import get_settings

        settings = get_settings()
    else:
        settings = effective_settings(conn)
    providers = [
        AlpacaProvider(settings),
        FredProvider(settings),
        SecEdgarProvider(settings),
        AlphaVantageProvider(settings),
    ]
    latest_runs = _latest_provider_runs(conn)
    statuses = []
    for provider in providers:
        status = provider.status().__dict__
        run = latest_runs.get(status["name"])
        if run:
            status["last_refresh"] = run["finished_at"]
            status["records"] = run["records"]
            status["error"] = run["error"]
            if run["status"] == "success" and run["records"] > 0:
                status["state"] = "live"
            elif run["status"] == "success":
                status["state"] = "checked"
            elif run["status"] == "failed":
                status["state"] = "error"
            else:
                status["state"] = run["status"]
        elif status["configured"]:
            status["state"] = "configured"
        statuses.append(status)
    return sorted(statuses, key=lambda item: item["priority"], reverse=True)
