"""Thin Prometheus HTTP API client that returns model-friendly, compact results (ADR-0006)."""

from __future__ import annotations

from typing import Any

import httpx2

from maestro_common.config import settings
from maestro_common.events import emit

_MAX_SERIES = 25


class PrometheusClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.prometheus_url).rstrip("/")

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(20.0)) as http:
            resp = await http.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "success":
            raise RuntimeError(f"prometheus error: {body.get('error', body)}")
        return body["data"]

    async def query(self, expr: str) -> str:
        """Instant query. Returns a compact text table the model can read."""
        data = await self._get("/api/v1/query", {"query": expr})
        text = _format_instant(data)
        emit("evidence.gathered", f"PromQL: {expr}", to="prometheus", detail={"query": expr, "result": text[:1500]})
        return text

    async def query_range(self, expr: str, minutes: int = 30, step: str = "60s") -> str:
        """Range query over the last N minutes; returns first/min/max/last per series."""
        import time

        end = time.time()
        data = await self._get(
            "/api/v1/query_range",
            {"query": expr, "start": end - minutes * 60, "end": end, "step": step},
        )
        text = _format_range(data, minutes)
        emit("evidence.gathered", f"PromQL range ({minutes}m): {expr}", to="prometheus", detail={"query": expr, "result": text[:1500]})
        return text

    async def targets(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/targets", {"state": "active"})
        return [
            {"job": t["labels"].get("job"), "instance": t["labels"].get("instance"), "health": t["health"]}
            for t in data.get("activeTargets", [])
        ]


def _labels(metric: dict[str, str]) -> str:
    name = metric.get("__name__", "")
    rest = ", ".join(f"{k}={v}" for k, v in sorted(metric.items()) if k != "__name__")
    return f"{name}{{{rest}}}" if rest else name or "{}"


def _num(v: str) -> str:
    try:
        f = float(v)
    except ValueError:
        return v
    if f.is_integer() and abs(f) < 1e12:
        return str(int(f))
    return f"{f:.4g}"


def _format_instant(data: dict[str, Any]) -> str:
    rtype = data.get("resultType")
    result = data.get("result", [])
    if rtype == "scalar":
        return _num(result[1])
    if not result:
        return "(no series matched)"
    lines = [f"{_labels(r['metric'])} = {_num(r['value'][1])}" for r in result[:_MAX_SERIES]]
    if len(result) > _MAX_SERIES:
        lines.append(f"... {len(result) - _MAX_SERIES} more series omitted")
    return "\n".join(lines)


def _format_range(data: dict[str, Any], minutes: int) -> str:
    result = data.get("result", [])
    if not result:
        return "(no series matched)"
    lines = []
    for r in result[:_MAX_SERIES]:
        vals = [float(v[1]) for v in r["values"] if v[1] not in ("NaN", "+Inf", "-Inf")]
        if not vals:
            continue
        lines.append(
            f"{_labels(r['metric'])}: first={_num(str(vals[0]))} min={_num(str(min(vals)))} "
            f"max={_num(str(max(vals)))} last={_num(str(vals[-1]))} over {minutes}m ({len(vals)} samples)"
        )
    if len(result) > _MAX_SERIES:
        lines.append(f"... {len(result) - _MAX_SERIES} more series omitted")
    return "\n".join(lines) or "(no numeric samples)"
