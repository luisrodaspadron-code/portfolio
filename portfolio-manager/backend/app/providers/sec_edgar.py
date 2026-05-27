from __future__ import annotations

import httpx

from app.config import Settings
from app.providers.base import ProviderStatus


class SecEdgarProvider:
    name = "sec_edgar"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> ProviderStatus:
        user_agent = self.settings.sec_user_agent.strip()
        configured = bool(user_agent and "contact@example.com" not in user_agent.lower())
        return ProviderStatus(
            name=self.name,
            configured=configured,
            capabilities=["company_facts", "submissions"],
            note="Company facts are used only when SEC_USER_AGENT identifies you with real contact information.",
            priority=70,
        )

    async def company_facts(self, cik: str) -> dict:
        if not self.status().configured:
            return {}
        padded = cik.zfill(10)
        headers = {"User-Agent": self.settings.sec_user_agent}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            response = await client.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json")
            response.raise_for_status()
            return response.json()

    async def company_tickers(self) -> dict:
        if not self.status().configured:
            return {}
        headers = {"User-Agent": self.settings.sec_user_agent}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            response = await client.get("https://www.sec.gov/files/company_tickers.json")
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
