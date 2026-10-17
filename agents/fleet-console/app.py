"""Fleet Console: event hub, incident intake, scenario controls and the executive UI (ADR-0009)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from maestro_common.auth import client_credentials_token, password_token
from maestro_common.config import settings
from maestro_common.events import new_trace_id
from maestro_common.metrics import REQUESTS

import scenarios

log = logging.getLogger("fleet-console")
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

MAESTRO_URL = os.environ.get("MAESTRO_URL", "http://maestro.maestro:8000").rstrip("/")
AUTH_MODES = ("exchange", "passthrough")  # ADR-0015: how Maestro authenticates to the domain agents
DOMAINS = ("apim", "cache", "messaging")
STATIC_DIR = Path(__file__).parent / "static"
RING_SIZE = 2000
REPLAY_SIZE = 200

NODE_IDS = {
    "console", "ide", "maestro", "gateway", "keycloak", "skills", "apim-agent", "cache-agent",
    "messaging-agent", "edge-gateway", "valkey", "kafka", "prometheus", "grafana", "portal",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Hub:
    """Ring buffer of events plus fan-out to SSE subscribers."""

    def __init__(self) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=RING_SIZE)
        self.by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.assessments: dict[str, dict[str, Any]] = {}
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def add(self, event: dict[str, Any]) -> dict[str, Any]:
        event.setdefault("ts", _now())
        event.setdefault("trace_id", "")
        event.setdefault("source", "unknown")
        self.events.append(event)
        if event["trace_id"]:
            self.by_trace[event["trace_id"]].append(event)
            if len(self.by_trace) > 200:  # keep the per-trace index bounded
                oldest = next(iter(self.by_trace))
                del self.by_trace[oldest]
        if event["kind"] == "assessment.posted":
            detail = event.get("detail") or {}
            payload = detail.get("assessment") if isinstance(detail.get("assessment"), dict) else detail
            if isinstance(payload, dict) and payload.get("verdict"):
                self.assessments[event["trace_id"]] = payload
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self.subscribers.discard(q)
        return event

    def publish(self, kind: str, summary: str, *, trace_id: str = "", to: str | None = None,
                detail: dict[str, Any] | None = None) -> dict[str, Any]:
        event: dict[str, Any] = {"ts": _now(), "trace_id": trace_id, "source": "console", "kind": kind, "summary": summary[:500]}
        if to:
            event["edge"] = {"from": "console", "to": to}
        if detail:
            event["detail"] = detail
        return self.add(event)


hub = Hub()
app = FastAPI(title="Maestro Fleet Console", docs_url=None, redoc_url=None)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    # Explicit route: the static-files mount at "/" would otherwise swallow the bare /metrics path.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

_incident_seq = 1000


# --- events ---------------------------------------------------------------------------
@app.post("/api/events", status_code=202)
async def post_event(request: Request) -> dict[str, str]:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, "body must be JSON")
    if not isinstance(body, dict) or not isinstance(body.get("kind"), str) or not isinstance(body.get("summary"), str):
        raise HTTPException(400, "event needs string 'kind' and 'summary'")
    edge = body.get("edge")
    if edge is not None and not (isinstance(edge, dict) and isinstance(edge.get("from"), str) and isinstance(edge.get("to"), str)):
        raise HTTPException(400, "edge must be {from, to}")
    hub.add(body)
    return {"status": "accepted"}


@app.get("/api/events")
async def list_events(trace_id: str | None = None) -> list[dict[str, Any]]:
    if trace_id:
        return list(hub.by_trace.get(trace_id, []))
    return list(hub.events)[-REPLAY_SIZE:]


@app.get("/api/stream")
async def stream() -> StreamingResponse:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=5000)
    hub.subscribers.add(queue)

    async def gen():
        try:
            yield ": connected\n\n"
            for ev in list(hub.events)[-REPLAY_SIZE:]:
                yield f"event: fleet\ndata: {json.dumps(ev)}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: fleet\ndata: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            hub.subscribers.discard(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- intake ---------------------------------------------------------------------------
def _auth_mode(body: dict[str, Any]) -> str | None:
    mode = body.get("auth_mode")
    if mode is None or mode == "":
        return None
    if mode not in AUTH_MODES:
        raise HTTPException(400, f"auth_mode must be one of {list(AUTH_MODES)}")
    return str(mode)


async def _ask_maestro(trace_id: str, question: str, auth_mode: str | None = None) -> None:
    try:
        token = await client_credentials_token()
        hub.publish("token.issued", "Console identity token issued by Keycloak (client-credentials)",
                    trace_id=trace_id, to="keycloak", detail={"client_id": settings.oidc_client_id or "fleet-console"})
    except Exception as exc:  # noqa: BLE001
        hub.publish("error", f"Could not obtain a token from Keycloak: {exc}", trace_id=trace_id, to="keycloak")
        REQUESTS.labels(settings.service_name, "ask", "token_error").inc()
        return
    body: dict[str, Any] = {"question": question, "trace_id": trace_id}
    if auth_mode:
        body["auth_mode"] = auth_mode
    hub.publish("request.sent", "Question sent to Maestro with the console's JWT" + (f" (delegation: {auth_mode})" if auth_mode else ""),
                trace_id=trace_id, to="maestro", detail={"question": question, "auth_mode": auth_mode or "default"})
    try:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(600.0, connect=10.0)) as http:
            resp = await http.post(f"{MAESTRO_URL}/api/ask", json=body, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        assessment = resp.json()
        if isinstance(assessment, dict) and assessment.get("verdict"):
            hub.assessments.setdefault(trace_id, assessment)
        REQUESTS.labels(settings.service_name, "ask", "ok").inc()
    except Exception as exc:  # noqa: BLE001
        log.warning("maestro call failed for %s: %s", trace_id, exc)
        hub.publish("error", f"Maestro did not return an assessment: {exc}", trace_id=trace_id, to="maestro")
        REQUESTS.labels(settings.service_name, "ask", "error").inc()


@app.post("/api/incident")
async def raise_incident(body: dict[str, Any]) -> dict[str, str]:
    global _incident_seq
    title = str(body.get("title") or "Member portal API returning 503s").strip()
    service = str(body.get("service") or "member-portal").strip()
    description = str(body.get("description") or "").strip()
    _incident_seq += 1
    inc = f"INC-{_incident_seq}"
    trace_id = new_trace_id()
    question = (f"P1 {inc}: {title} — service {service}. {description} "
                "Determine which domains are implicated and recommend the next step.").replace("  ", " ")
    auth_mode = _auth_mode(body)
    hub.publish("incident.raised", f"P1 {inc} raised: {title}", trace_id=trace_id, to="maestro",
                detail={"incident": inc, "title": title, "service": service, "description": description, "question": question,
                        "auth_mode": auth_mode or "default"})
    asyncio.create_task(_ask_maestro(trace_id, question, auth_mode))
    return {"trace_id": trace_id, "incident": inc}


@app.post("/api/ask")
async def ask(body: dict[str, Any]) -> dict[str, str]:
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question is required")
    auth_mode = _auth_mode(body)
    trace_id = new_trace_id()
    hub.publish("question.asked", question[:200], trace_id=trace_id, to="maestro",
                detail={"question": question, "auth_mode": auth_mode or "default"})
    asyncio.create_task(_ask_maestro(trace_id, question, auth_mode))
    return {"trace_id": trace_id}


# --- identity sandbox (ADR-0015) -------------------------------------------------------
@app.post("/api/identity/try")
async def identity_try(body: dict[str, Any]) -> dict[str, Any]:
    """Perform one real on-behalf-of exchange for a demo identity and return both tokens' claims.

    The console fetches the subject's own token (a demo user via the public IDE client, or its own
    service account), then asks Maestro to delegate — exactly what happens during an incident. Maestro
    is the only component holding the `maestro` client secret, so the exchange itself happens there.
    No raw token is returned.
    """
    user = str(body.get("user") or "engineer").strip()
    domain = str(body.get("domain") or "apim").strip()
    if domain not in DOMAINS:
        raise HTTPException(400, f"domain must be one of {list(DOMAINS)}")
    creds = _credentials()
    try:
        if user == (settings.oidc_client_id or "fleet-console"):
            subject = await client_credentials_token()
        else:
            demo = next((u for u in creds.get("demo_users", []) if u.get("username") == user), None)
            if demo is None:
                raise HTTPException(404, f"unknown demo identity {user!r}")
            subject = await password_token(demo["username"], demo["password"])
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Keycloak did not issue a token for {user}: {exc}")
    try:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(20.0)) as http:
            resp = await http.post(f"{MAESTRO_URL}/api/delegate", json={"audience": f"{domain}-agent", "scope": f"domain-{domain}"},
                                   headers={"Authorization": f"Bearer {subject}"})
        resp.raise_for_status()
        out = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Maestro could not perform the exchange: {exc}")
    out.update({"user": user, "domain": domain, "audience": f"{domain}-agent", "scope": f"domain-{domain}"})
    return out


@app.get("/api/assessment/{trace_id}")
async def get_assessment(trace_id: str) -> dict[str, Any]:
    if trace_id not in hub.assessments:
        raise HTTPException(404, "no assessment for this trace yet")
    return hub.assessments[trace_id]


# --- scenarios ------------------------------------------------------------------------
@app.get("/api/scenarios")
async def get_scenarios() -> list[dict[str, Any]]:
    return await asyncio.to_thread(scenarios.list_scenarios)


def _scenario_or_404(name: str) -> scenarios.Scenario:
    if name not in scenarios.SCENARIOS:
        raise HTTPException(404, f"unknown scenario {name!r}")
    return scenarios.SCENARIOS[name]


@app.post("/api/scenarios/{name}")
async def apply_scenario(name: str) -> dict[str, Any]:
    s = _scenario_or_404(name)
    try:
        await asyncio.to_thread(scenarios.apply, name)
    except (scenarios.ScenarioUnavailable, RuntimeError) as exc:
        raise HTTPException(503, str(exc))
    hub.publish("scenario.applied", f"Fault injected: {s.title}", to=s.platform_node,
                detail={"scenario": name, "domain": s.domain, "description": s.description})
    return {"name": name, "active": True}


@app.delete("/api/scenarios/{name}")
async def clear_scenario(name: str) -> dict[str, Any]:
    s = _scenario_or_404(name)
    try:
        await asyncio.to_thread(scenarios.clear, name)
    except (scenarios.ScenarioUnavailable, RuntimeError) as exc:
        raise HTTPException(503, str(exc))
    hub.publish("scenario.cleared", f"Fault cleared: {s.title}", to=s.platform_node,
                detail={"scenario": name, "domain": s.domain})
    return {"name": name, "active": False}


# --- topology -------------------------------------------------------------------------
def _topology() -> dict[str, Any]:
    gw = settings.public_gateway_url.rstrip("/")
    nodes = [
        {"id": "console", "label": "Fleet Console", "sublabel": "incident intake · P1", "column": "consumers"},
        {"id": "ide", "label": "Engineer in IDE", "sublabel": "Claude Code · Copilot · MCP", "column": "consumers",
         "url": f"{gw}/maestro/mcp" if gw else None},
        {"id": "maestro", "label": "Maestro", "sublabel": "orchestrator · agent of agents", "column": "orchestration"},
        {"id": "keycloak", "label": "Keycloak", "sublabel": "identity · JWT issuer", "column": "identity",
         "url": settings.public_keycloak_url or None},
        {"id": "gateway", "label": "Fleet gateway", "sublabel": "agentgateway · JWT authn · tool RBAC · audit",
         "column": "gateway", "url": f"{gw}/ui" if gw else None},
        {"id": "skills", "label": "skills/", "sublabel": "SKILL.md bundles · pinned", "column": "agents"},
        {"id": "apim-agent", "label": "apim-agent", "sublabel": "API Management", "column": "agents"},
        {"id": "cache-agent", "label": "cache-agent", "sublabel": "Distributed Cache", "column": "agents"},
        {"id": "messaging-agent", "label": "messaging-agent", "sublabel": "Messaging", "column": "agents"},
        {"id": "edge-gateway", "label": "Edge gateway", "sublabel": "gateways · routes", "column": "platforms",
         "url": settings.public_edge_url or None},
        {"id": "valkey", "label": "Valkey", "sublabel": "clusters · keyspace", "column": "platforms"},
        {"id": "kafka", "label": "Kafka", "sublabel": "topics · consumer groups", "column": "platforms"},
        {"id": "portal", "label": "Member portal", "sublabel": "sample business app", "column": "platforms"},
        {"id": "prometheus", "label": "Prometheus", "sublabel": "metrics", "column": "monitoring",
         "url": settings.public_prometheus_url or None},
        {"id": "grafana", "label": "Grafana", "sublabel": "dashboards", "column": "monitoring",
         "url": settings.public_grafana_url or None},
    ]
    edges = [
        ["console", "keycloak"], ["console", "maestro"], ["ide", "gateway"], ["maestro", "gateway"], ["gateway", "maestro"],
        ["keycloak", "gateway"], ["maestro", "keycloak"], ["maestro", "skills"],
        ["gateway", "apim-agent"], ["gateway", "cache-agent"], ["gateway", "messaging-agent"],
        ["apim-agent", "skills"], ["cache-agent", "skills"], ["messaging-agent", "skills"],
        ["apim-agent", "edge-gateway"], ["cache-agent", "valkey"], ["messaging-agent", "kafka"],
        ["apim-agent", "prometheus"], ["cache-agent", "prometheus"], ["messaging-agent", "prometheus"],
        ["edge-gateway", "prometheus"], ["valkey", "prometheus"], ["kafka", "prometheus"], ["portal", "prometheus"],
        ["grafana", "prometheus"], ["edge-gateway", "portal"], ["portal", "valkey"], ["portal", "kafka"],
    ]
    return {"nodes": nodes, "edges": [{"from": a, "to": b} for a, b in edges],
            "urls": {"grafana": settings.public_grafana_url, "prometheus": settings.public_prometheus_url,
                     "keycloak": settings.public_keycloak_url, "gateway_ui": f"{gw}/ui" if gw else "",
                     "edge": settings.public_edge_url},
            "credentials": _credentials(),
            # ADR-0015: how Maestro authenticates to the agents by default, and the audiences it can delegate to.
            "identity": {"delegation": os.environ.get("MAESTRO_AUTH_MODE", "exchange").strip() or "exchange",
                         "modes": list(AUTH_MODES), "domains": list(DOMAINS),
                         "agent_audiences": [f"{d}-agent" for d in DOMAINS],
                         "obo_lifetime_s": 300}}


def _credentials() -> dict[str, Any]:
    """Demo credentials for the hover cards. Public by design: the stack holds no sensitive data.
    The chart passes them as DEMO_CREDENTIALS (JSON) from values.yaml `demo:`; the fallback mirrors docs/contracts.md."""
    raw = os.environ.get("DEMO_CREDENTIALS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            data["demo_users"] = data.pop("users", [])
            data["service_accounts"] = data.pop("serviceAccounts", [])
            return data
        except (json.JSONDecodeError, AttributeError) as exc:
            log.warning("DEMO_CREDENTIALS is not valid JSON: %s", exc)
    return {
        "grafana": {"username": "admin", "password": "maestro-demo", "note": "anonymous viewing is also enabled"},
        "keycloak": {"username": "admin", "password": "maestro-demo", "note": "realm: maestro"},
        "gateway": {"note": "no login; read-only admin UI"},
        "prometheus": {"note": "no login"},
        "edge": {"note": "no login; try GET /api/members/42"},
        "demo_users": [
            {"username": "engineer", "password": "engineer", "roles": ["maestro:ask", "domain:apim", "domain:cache"]},
            {"username": "sre-lead", "password": "sre-lead", "roles": ["maestro:ask", "domain:apim", "domain:cache", "domain:messaging"]},
        ],
        "service_accounts": [{"client_id": "fleet-console", "secret": "fleet-console-secret"}, {"client_id": "maestro", "secret": "maestro-secret"}],
    }


@app.get("/api/topology")
async def topology() -> dict[str, Any]:
    return _topology()


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"service": settings.service_name, "status": "ok", "events": len(hub.events),
                         "subscribers": len(hub.subscribers)})


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
