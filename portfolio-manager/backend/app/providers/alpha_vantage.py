from __future__ import annotations

import httpx

from app.config import Settings
from app.providers.base import ProviderStatus


class AlphaVantageProvider:
    name = "alpha_vantage"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            configured=bool(self.settings.alpha_vantage_api_key),
            capabilities=["daily_adjusted_prices", "fundamentals", "technical_indicators", "crypto"],
            note="Fallback daily market-data source when live Alpaca coverage is unavailable or incomplete.",
            priority=60,
        )

    async def daily_adjusted(self, symbol: str) -> dict:
        if not self.status().configured:
            return {}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "TIME_SERIES_DAILY_ADJUSTED",
                    "symbol": symbol,
                    "apikey": self.settings.alpha_vantage_api_key,
                    "outputsize": "compact",
                },
            )
            response.raise_for_status()
            return response.json()
