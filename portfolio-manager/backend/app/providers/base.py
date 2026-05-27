from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ProviderStatus:
    name: str
    configured: bool
    capabilities: list[str]
    note: str
    priority: int = 0
    state: str = "standby"
    last_refresh: str | None = None
    records: int = 0
    error: str = ""


class MarketDataProvider(Protocol):
    name: str

    def status(self) -> ProviderStatus:
        ...

    async def fetch(self, *args: Any, **kwargs: Any) -> Any:
        ...
