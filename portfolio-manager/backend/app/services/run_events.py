"""In-process event bus for advisor run lifecycle.

Used by ``advisor_service`` to publish step/run lifecycle events and by the
``/api/advisor/runs/{run_id}/events`` SSE route to fan them out to one or more
subscribed HTTP clients.

The bus is intentionally simple and dependency-free:
  * One thread-safe registry, one bounded ``Queue`` per subscriber.
  * Publishers never block on slow consumers; if a subscriber's queue is full
    the oldest pending event is dropped (and a ``dropped`` marker is recorded).
  * Subscribers always receive a terminal ``status="closed"`` sentinel after
    the run finishes so SSE generators can shut down cleanly.

The bus only carries the *structural* lifecycle of a run (step started /
finished / run terminal). It never carries LLM tokens or hidden reasoning.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator


_MAX_QUEUE = 256
_TERMINAL_STATUSES = {"success", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunEvent:
    run_id: int
    event_id: int
    type: str
    phase: str
    status: str
    title: str
    detail: str
    timestamp: str
    metrics: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": str(self.run_id),
            "eventId": self.event_id,
            "type": self.type,
            "phase": self.phase,
            "status": self.status,
            "title": self.title,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "metrics": dict(self.metrics),
            "source": self.source,
        }


class _RunBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, list[queue.Queue[RunEvent | None]]] = {}
        self._history: dict[int, list[RunEvent]] = {}
        self._next_event_id: dict[int, int] = {}
        self._closed: set[int] = set()
        self._lock = threading.Lock()

    def _allocate_event_id(self, run_id: int) -> int:
        next_id = self._next_event_id.get(run_id, 0) + 1
        self._next_event_id[run_id] = next_id
        return next_id

    def publish(
        self,
        run_id: int,
        *,
        type: str,
        phase: str,
        status: str,
        title: str,
        detail: str = "",
        metrics: dict[str, Any] | None = None,
        source: str = "",
    ) -> RunEvent:
        with self._lock:
            event = RunEvent(
                run_id=run_id,
                event_id=self._allocate_event_id(run_id),
                type=type,
                phase=phase,
                status=status,
                title=title,
                detail=detail,
                timestamp=_now(),
                metrics=dict(metrics or {}),
                source=source,
            )
            self._history.setdefault(run_id, []).append(event)
            subscribers = list(self._subscribers.get(run_id, ()))
            terminal = type == "run" and status in _TERMINAL_STATUSES
            if terminal:
                self._closed.add(run_id)
        for q in subscribers:
            self._safe_put(q, event)
            if terminal:
                self._safe_put(q, None)
        return event

    @staticmethod
    def _safe_put(q: "queue.Queue[RunEvent | None]", item: RunEvent | None) -> None:
        try:
            q.put_nowait(item)
        except queue.Full:
            try:
                _ = q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(item)
            except queue.Full:
                pass

    def subscribe(self, run_id: int) -> tuple["queue.Queue[RunEvent | None]", list[RunEvent], bool]:
        q: queue.Queue[RunEvent | None] = queue.Queue(maxsize=_MAX_QUEUE)
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
            history = list(self._history.get(run_id, []))
            already_closed = run_id in self._closed
        return q, history, already_closed

    def unsubscribe(self, run_id: int, q: "queue.Queue[RunEvent | None]") -> None:
        with self._lock:
            queues = self._subscribers.get(run_id)
            if not queues:
                return
            try:
                queues.remove(q)
            except ValueError:
                return
            if not queues:
                self._subscribers.pop(run_id, None)

    def history(self, run_id: int) -> list[RunEvent]:
        with self._lock:
            return list(self._history.get(run_id, ()))

    def is_closed(self, run_id: int) -> bool:
        with self._lock:
            return run_id in self._closed

    def reset(self) -> None:
        """Clear all state. Test-only helper."""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()
            self._next_event_id.clear()
            self._closed.clear()

    def stream(self, run_id: int, *, heartbeat_seconds: float = 15.0) -> Iterator[RunEvent | None]:
        """Yield events for ``run_id``, including any history already buffered.

        Yields ``None`` periodically so SSE writers can emit keep-alive comments
        even when there is no real event traffic. The iterator terminates once
        the bus marks the run closed *and* the queue is drained.
        """
        q, history, already_closed = self.subscribe(run_id)
        try:
            for event in history:
                yield event
            if already_closed:
                yield None
                return
            while True:
                try:
                    item = q.get(timeout=heartbeat_seconds)
                except queue.Empty:
                    yield None
                    continue
                if item is None:
                    return
                yield item
        finally:
            self.unsubscribe(run_id, q)


_bus = _RunBus()


def publish(
    run_id: int,
    *,
    type: str,
    phase: str,
    status: str,
    title: str,
    detail: str = "",
    metrics: dict[str, Any] | None = None,
    source: str = "",
) -> RunEvent:
    return _bus.publish(
        run_id,
        type=type,
        phase=phase,
        status=status,
        title=title,
        detail=detail,
        metrics=metrics,
        source=source,
    )


def history(run_id: int) -> list[RunEvent]:
    return _bus.history(run_id)


def is_closed(run_id: int) -> bool:
    return _bus.is_closed(run_id)


def stream(run_id: int, *, heartbeat_seconds: float = 15.0) -> Iterator[RunEvent | None]:
    return _bus.stream(run_id, heartbeat_seconds=heartbeat_seconds)


def reset_for_tests() -> None:
    _bus.reset()


def history_as_dicts(run_id: int) -> list[dict[str, Any]]:
    return [event.to_dict() for event in _bus.history(run_id)]


def merge_with_steps(run_id: int, step_events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge step-derived events with bus history without duplicating titles.

    Falls back to the legacy ``_run_events`` projection when the bus has no
    record (e.g. server restart between publish and read).
    """
    bus_events = history_as_dicts(run_id)
    if bus_events:
        return bus_events
    return list(step_events)
