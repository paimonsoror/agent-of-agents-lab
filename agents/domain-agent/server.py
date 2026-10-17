"""Domain agent MCP server: one image, parameterised by AGENT_DOMAIN (ADR-0008).

Exposes exactly two tools — `assess` and `health` — behind Keycloak JWT verification.
Everything domain-specific is in domains/<domain>.py and in the skills it loads.
"""

from __future__ import annotations

import importlib
import logging
import re
import time
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import MCPServer

from maestro_common import settings
from maestro_common.auth import KeycloakTokenVerifier, auth_settings, caller_from_access_token
from maestro_common.events import current_caller, current_trace, emit, new_trace_id
from maestro_common.llm import LLMLoop
from maestro_common.metrics import REQUESTS, REQUEST_SECONDS
from maestro_common.skills import Skill, load_skills, render_system_prompt

from finding import FINDING_OUTPUT_SCHEMA, PREAMBLE, user_prompt
from tools_common import build_common_tools

log = logging.getLogger(__name__)


def build_mcp() -> tuple[MCPServer, ModuleType]:
    if not settings.agent_domain:
        raise RuntimeError("AGENT_DOMAIN must be set (apim | cache | messaging)")
    domain: ModuleType = importlib.import_module(f"domains.{settings.agent_domain}")
    skills: list[Skill] = load_skills(settings.agent_skills, settings.skills_dir)
    system = PREAMBLE.format(agent=settings.service_name, domain=settings.agent_domain) + "\n\n" + render_system_prompt(skills)
    tools = build_common_tools(skills) + domain.build_tools()
    log.info("domain=%s skills=%s tools=%s", settings.agent_domain, [s.name for s in skills], [t.name for t in tools])

    mcp = MCPServer(
        name=settings.service_name,
        instructions=f"Observability agent for the {settings.agent_domain} domain. Call assess(question) to get a Finding.",
        token_verifier=KeycloakTokenVerifier(),
        auth=auth_settings(f"http://{settings.service_name}:8000/mcp"),
    )

    @mcp.tool()
    async def assess(question: str, trace_id: str = "") -> dict[str, Any]:
        """Assess whether this domain is implicated in the described problem. Returns a Finding: implicated, confidence, headline, summary, evidence, recommended_actions."""
        trace = trace_id or new_trace_id()
        current_trace.set(trace)
        caller = caller_from_access_token(get_access_token())
        caller_info = caller.as_dict() if caller else {}
        current_caller.set(caller_info)
        started = time.perf_counter()

        who = caller.display if caller else "unknown"
        presented = (f" on behalf of {who}, presented by {caller_info.get('azp')} (on-behalf-of token for {', '.join(caller_info.get('aud', []))})"
                     if caller_info.get("delegated") else f" from {who}")
        emit("request.received", f"{settings.service_name} received assess{presented}: {question[:140]}",
             from_="gateway", to=settings.service_name, detail={"caller": caller_info, "question": question})
        emit("skills.loaded", "Loaded skills: " + ", ".join(f"{s.name}@{s.version}" for s in skills), to="skills",
             detail={"skills": [{"name": s.name, "version": s.version, "references": list(s.references)} for s in skills]})

        loop = LLMLoop(system=system, tools=tools, output_schema=FINDING_OUTPUT_SCHEMA)
        try:
            result = await loop.run(user_prompt(question, trace, caller_info, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                settings.grafana_public_url))
        except Exception as exc:
            REQUESTS.labels(settings.service_name, "assess", "error").inc()
            emit("error", f"{settings.service_name} assess failed: {exc}"[:300])
            raise

        analytic = result.structured or {
            "implicated": False,
            "confidence": 0.0,
            "headline": "Agent could not produce a structured finding",
            "summary": result.text[:1000],
            "evidence": [],
            "recommended_actions": ["Re-run the assessment; inspect the agent logs."],
        }
        for item in analytic.get("evidence", []) or []:
            if isinstance(item, dict):
                item["link"] = _normalise_link(item.get("link", ""))
        finding = {
            "domain": settings.agent_domain,
            "agent": settings.service_name,
            "trace_id": trace,
            **analytic,
            "skills_used": [s.name for s in skills],
            # Who this finding was produced for (sub) and who presented the token (azp/act) — ADR-0015.
            "caller": {k: caller_info.get(k, "" if k not in ("aud", "roles", "delegated") else ([] if k != "delegated" else False))
                       for k in ("sub", "username", "azp", "act", "delegated", "aud", "roles")},
            "model": result.model,
            "turns": result.turns,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        emit("finding.returned",
             f"{finding['headline']} (implicated={finding['implicated']}, confidence={finding['confidence']:.2f})",
             to="maestro", detail=finding)
        REQUESTS.labels(settings.service_name, "assess", "ok").inc()
        REQUEST_SECONDS.labels(settings.service_name, "assess").observe(time.perf_counter() - started)
        return finding

    @mcp.tool()
    async def health() -> dict[str, Any]:
        """Report the agent's status and whether its platform and the shared monitoring are reachable."""
        return await _health(domain, skills)

    return mcp, domain


_PLACEHOLDER_HOST = re.compile(r"^https?://(<?grafana>?|\$?\{?GRAFANA_PUBLIC_URL\}?|grafana[^/]*)(/|$)", re.IGNORECASE)


def _normalise_link(link: str) -> str:
    """Rewrite placeholder Grafana hosts the model may emit onto the real public URL; pass real URLs through."""
    base = settings.grafana_public_url.rstrip("/")
    link = (link or "").strip()
    if not link or not base:
        return link
    if link.startswith("/d/"):
        return base + link
    if _PLACEHOLDER_HOST.match(link) and not link.startswith(base):
        return base + "/" + _PLACEHOLDER_HOST.sub("", link)
    return link


async def _health(domain: ModuleType, skills: list[Skill]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent": settings.service_name,
        "domain": settings.agent_domain,
        "model": settings.llm_model,
        "skills": [f"{s.name}@{s.version}" for s in skills],
    }
    try:
        platform = domain.health()
        if hasattr(platform, "__await__"):
            platform = await platform
        payload["platform"] = platform
    except Exception as exc:  # noqa: BLE001
        payload["platform"] = {"status": "unreachable", "error": str(exc)}
    return payload


def health_check_for(domain: ModuleType, skills: list[Skill]):
    async def check() -> dict[str, Any]:
        return await _health(domain, skills)

    return check
