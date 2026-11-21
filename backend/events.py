"""In-process event bus feeding the SSE stream."""
from __future__ import annotations

import threading
import time
from typing import Any


class EventBus:
    def __init__(self, maxlen: int = 2000) -> None:
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._next = 1
        self._maxlen = maxlen

    def publish(self, kind: str, agent: str, message: str, dispute_id: str | None = None,
                data: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            ev = {"id": self._next, "ts": time.time(), "kind": kind, "agent": agent,
                  "message": message, "dispute_id": dispute_id, "data": data or {}}
            self._next += 1
            self._events.append(ev)
            if len(self._events) > self._maxlen:
                self._events = self._events[-self._maxlen :]
        return ev

    def since(self, last_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._events if e["id"] > last_id]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


bus = EventBus()
