"""Best-effort event emission to the Fleet Console event hub (ADR-0009).

Every component calls `emit(...)` as it works. The current trace id is carried in a
ContextVar so tools deep inside an LLM loop do not have to thread it through. Emission
never blocks or fails the request path: events are queued and posted by a background
thread, and dropped if the hub is unreachable.
"""

from __future__ import annotations

import contextvars
import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx2

from maestro_common.config import settings

log = logging.getLogger(__name__)

current_trace: contextvars.ContextVar[str] = contextvars.ContextVar("maestro_trace", default="")
current_caller: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("maestro_caller", default={})


def new_trace_id() -> str:
    return "trc-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


class _Emitter:
    def __init__(self, url: str, source: str) -> None:
        self.url = url
        self.source = source
        self._q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread or not self.url:
            return
        self._thread = threading.Thread(target=self._run, name="fleet-events", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        with httpx2.Client(timeout=httpx2.Timeout(3.0)) as client:
            while True:
                event = self._q.get()
                try:
                    client.post(self.url, json=event)
                except Exception as exc:  # noqa: BLE001 - telemetry must never raise
                    log.debug("event drop (%s): %s", exc.__class__.__name__, event.get("kind"))

    def emit(self, event: dict[str, Any]) -> None:
        if not self.url:
            return
        self.start()
        try:
            self._q.put_nowait(event)
        except queue.Full:
            log.debug("event queue full; dropping %s", event.get("kind"))


_emitter = _Emitter(settings.fleet_events_url, settings.service_name)


def emit(
    kind: str,
    summary: str,
    *,
    trace_id: str | None = None,
    to: str | None = None,
    from_: str | None = None,
    detail: dict[str, Any] | None = None,
    source: str | None = None,
) -> None:
    """Queue one event. `to` draws an edge from this service (or `from_`) to the target node."""
    event: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "trace_id": trace_id or current_trace.get(),
        "source": source or _emitter.source,
        "kind": kind,
        "summary": summary[:500],
    }
    if to:
        event["edge"] = {"from": from_ or _emitter.source, "to": to}
    if detail:
        event["detail"] = _jsonable(detail)
    _emitter.emit(event)


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))
