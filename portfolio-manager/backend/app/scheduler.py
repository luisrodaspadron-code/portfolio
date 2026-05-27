from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.advisor_service import run_advisor_cycle


class LocalScheduler:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.last_run_at: str | None = None
        self.last_result: dict[str, Any] | None = None
        self.started_at: str | None = None
        self.interval_seconds = 24 * 60 * 60

    def start(self, interval_seconds: int = 24 * 60 * 60) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.interval_seconds = interval_seconds
        self.started_at = datetime.now(timezone.utc).isoformat()

        def loop() -> None:
            while not self._stop.wait(interval_seconds):
                self.last_run_at = datetime.now(timezone.utc).isoformat()
                self.last_result = run_advisor_cycle(trigger="scheduled")

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        anchor = self.last_run_at or self.started_at
        next_run_at = None
        if anchor:
            next_run_at = (datetime.fromisoformat(anchor) + timedelta(seconds=self.interval_seconds)).isoformat()
        return {
            "enabled": bool(self._thread and self._thread.is_alive()),
            "cadence": "daily",
            "last_run_at": self.last_run_at,
            "next_run_at": next_run_at,
            "interval_seconds": self.interval_seconds,
            "last_result": self.last_result,
        }


scheduler = LocalScheduler()
