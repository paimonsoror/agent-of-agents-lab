"""API-management domain tools: the edge gateway (agentgateway) and its declarative config.

The edge gateway's config is a ConfigMap; change management annotates it with
maestro.io/* keys (ADR-0011). The agent reads both through the Kubernetes API with a
namespaced, read-only Role, and probes routes through the gateway itself.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx2
import yaml
from kubernetes import client as k8s
from kubernetes import config as k8s_config
from kubernetes.config.config_exception import ConfigException

from maestro_common import settings
from maestro_common.events import emit
from maestro_common.llm import ToolSpec

NODE = "edge-gateway"
_ANNOTATION_PREFIX = "maestro.io/"


def _core() -> k8s.CoreV1Api:
    try:
        k8s_config.load_incluster_config()
    except ConfigException:
        k8s_config.load_kube_config()
    return k8s.CoreV1Api()


def _configmap_ref() -> tuple[str, str]:
    ns, _, name = settings.edge_configmap.partition("/")
    if not name:
        raise RuntimeError("EDGE_CONFIGMAP must be <namespace>/<name>")
    return ns, name


def _read_configmap() -> tuple[dict[str, Any], dict[str, str], str]:
    ns, name = _configmap_ref()
    cm = _core().read_namespaced_config_map(name, ns)
    raw = (cm.data or {}).get("config.yaml", "")
    cfg = yaml.safe_load(raw) or {}
    annotations = {k: v for k, v in (cm.metadata.annotations or {}).items() if k.startswith(_ANNOTATION_PREFIX)}
    return cfg, annotations, cm.metadata.resource_version or ""


def _extract_routes(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = list(cfg.get("routes") or [])
    for bind in cfg.get("binds") or []:
        for listener in bind.get("listeners") or []:
            routes.extend(listener.get("routes") or [])
    out = []
    for i, r in enumerate(routes):
        backends = []
        for b in r.get("backends") or []:
            if "host" in b:
                backends.append({"type": "http", "host": b["host"]})
            elif "mcp" in b:
                backends.append({"type": "mcp", "targets": [t.get("name") for t in b["mcp"].get("targets", [])]})
            else:
                backends.append({"type": next(iter(b), "unknown")})
        out.append({
            "name": r.get("name", f"route{i}"),
            "matches": [m.get("path") for m in r.get("matches") or []] or ["/"],
            "backends": backends,
            "policies": sorted((r.get("policies") or {}).keys()),
        })
    return out


async def _get_edge_routes(_: dict[str, Any]) -> dict[str, Any]:
    cfg, annotations, rv = await asyncio.to_thread(_read_configmap)
    routes = _extract_routes(cfg)
    gateways = {name: {"port": g.get("port")} for name, g in (cfg.get("gateways") or {}).items()}
    emit("evidence.gathered", f"Read edge gateway config: {len(routes)} routes (rv {rv})", to=NODE,
         detail={"routes": routes, "annotations": annotations})
    return {"gateways": gateways, "routes": routes, "change_annotations": annotations, "resource_version": rv}


async def _get_edge_change_history(_: dict[str, Any]) -> dict[str, Any]:
    _, annotations, rv = await asyncio.to_thread(_read_configmap)
    strip = {k[len(_ANNOTATION_PREFIX):]: v for k, v in annotations.items()}
    pending = strip.get("change-id")
    summary = (
        f"Open change {pending}: {strip.get('change-summary', '')} at {strip.get('changed-at', '?')} by {strip.get('changed-by', '?')}"
        if pending
        else f"No open change; last rollback: {strip.get('last-rollback', 'none')}"
    )
    emit("evidence.gathered", summary, to=NODE, detail=strip)
    return {"open_change": pending, "annotations": strip, "resource_version": rv, "summary": summary}


async def _probe_edge_route(args: dict[str, Any]) -> dict[str, Any]:
    path = args["path"] if args["path"].startswith("/") else "/" + args["path"]
    url = settings.edge_gateway_url.rstrip("/") + path
    started = time.perf_counter()
    try:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(10.0)) as http:
            resp = await http.get(url)
        outcome = {"url": url, "status": resp.status_code, "latency_ms": int((time.perf_counter() - started) * 1000),
                   "body": resp.text[:300]}
    except Exception as exc:  # noqa: BLE001 - the model needs the failure as data
        outcome = {"url": url, "status": None, "latency_ms": int((time.perf_counter() - started) * 1000), "error": str(exc)}
    emit("evidence.gathered", f"Probed {path} via edge gateway → {outcome.get('status') or outcome.get('error')}", to=NODE, detail=outcome)
    return outcome


def build_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="get_edge_routes",
            description="Read the edge gateway's live declarative config: gateways, routes (name, path matches, backends, policies) and any maestro.io change annotations.",
            input_schema={"type": "object", "properties": {}},
            handler=_get_edge_routes,
        ),
        ToolSpec(
            name="get_edge_change_history",
            description="Read change-management annotations on the edge gateway config: open change id, summary, when and by whom, and the last rollback.",
            input_schema={"type": "object", "properties": {}},
            handler=_get_edge_change_history,
        ),
        ToolSpec(
            name="probe_edge_route",
            description="Send one GET through the edge gateway to a path (e.g. /api/members) and report status, latency and a body snippet.",
            input_schema={"type": "object", "properties": {"path": {"type": "string", "description": "Path to probe, e.g. /api/members"}}},
            handler=_probe_edge_route,
        ),
    ]


async def health() -> dict[str, Any]:
    _, annotations, rv = await asyncio.to_thread(_read_configmap)
    async with httpx2.AsyncClient(timeout=httpx2.Timeout(5.0)) as http:
        resp = await http.get(settings.edge_gateway_url.rstrip("/") + "/api/health")
    return {"status": "ok", "edge_gateway_http": resp.status_code, "config_resource_version": rv,
            "open_change": annotations.get(_ANNOTATION_PREFIX + "change-id")}
