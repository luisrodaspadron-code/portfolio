from __future__ import annotations

import httpx

from app.config import Settings
from app.providers.base import ProviderStatus


class FredProvider:
    name = "fred"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            configured=bool(self.settings.fred_api_key),
            capabilities=["macro_series"],
            note="Optional macro adapter for FRED series such as FEDFUNDS, CPI, unemployment, and Treasury yields.",
            priority=80,
        )

    async def observations(self, series_id: str, observation_start: str | None = None) -> dict:
        if not self.status().configured:
            return {}
        params = {
            "series_id": series_id,
            "api_key": self.settings.fred_api_key,
            "file_type": "json",
        }
        if observation_start:
            params["observation_start"] = observation_start
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params=params,
            )
            response.raise_for_status()
            return response.json()
