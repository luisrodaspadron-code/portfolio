from __future__ import annotations

import httpx

from app.config import Settings
from app.providers.base import ProviderStatus


class AlpacaProvider:
    name = "alpaca"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> ProviderStatus:
        configured = bool(self.settings.alpaca_api_key and self.settings.alpaca_secret_key)
        return ProviderStatus(
            name=self.name,
            configured=configured,
            capabilities=["latest_minute_equity_bars", "paper_trading_context"],
            note="Preferred live/recent market-data source when API keys are configured. No real orders are placed.",
            priority=100,
        )

    async def latest_bars(self, symbols: list[str]) -> dict:
        if not self.status().configured:
            return {}
        headers = {
            "APCA-API-KEY-ID": self.settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://data.alpaca.markets/v2/stocks/bars/latest",
                params={"symbols": ",".join(symbols)},
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def assets(self) -> list[dict]:
        if not self.status().configured:
            return []
        headers = {
            "APCA-API-KEY-ID": self.settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://paper-api.alpaca.markets/v2/assets",
                params={"status": "active", "asset_class": "us_equity"},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else []
