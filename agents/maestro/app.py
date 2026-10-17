"""Maestro: HTTP API for the Fleet Console (/api/ask, /api/delegate) and an MCP server for IDEs (/mcp), one process on :8000."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel
from starlette.routing import Mount

import federation
import orchestrator
from maestro_common import settings
from maestro_common.auth import (
    JWTError,
    KeycloakTokenVerifier,
    TokenExchangeError,
    auth_settings,
    caller_from_access_token,
    exchange_request,
    exchange_token,
    verify_bearer,
)
from maestro_common.events import new_trace_id
from maestro_common.server import build_app

mcp = MCPServer(
    name="maestro",
    instructions="Maestro, the agent of agents for observability. Call ask_maestro(question) to get a consolidated assessment across domains.",
    token_verifier=KeycloakTokenVerifier(),
    auth=auth_settings("http://maestro:8000/mcp"),
)


@mcp.tool()
async def ask_maestro(question: str) -> dict[str, Any]:
    """Ask Maestro to assess a problem across every technology domain you are entitled to see. Returns an Assessment with implicated/cleared domains, evidence and the next step."""
    caller = caller_from_access_token(get_access_token())
    if caller is None:
        raise ValueError("unauthenticated: a Keycloak bearer token is required")
    return await orchestrator.run_assessment(question, new_trace_id(), caller)


class AskBody(BaseModel):
    question: str
    trace_id: str | None = None
    auth_mode: str | None = None  # "exchange" (default, ADR-0015) or "passthrough" (ADR-0005), per request for demos


class DelegateBody(BaseModel):
    audience: str
    scope: str | None = None


api = FastAPI(title="Maestro API", docs_url=None, redoc_url=None)


async def _caller(authorization: str | None):
    try:
        return await asyncio.to_thread(verify_bearer, authorization)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@api.post("/ask")
async def ask(body: AskBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    caller = await _caller(authorization)
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    if body.auth_mode is not None and body.auth_mode not in federation.AUTH_MODES:
        raise HTTPException(status_code=400, detail=f"auth_mode must be one of {list(federation.AUTH_MODES)}")
    return await orchestrator.run_assessment(body.question.strip(), body.trace_id or new_trace_id(), caller, body.auth_mode)


@api.post("/delegate")
async def delegate(body: DelegateBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Identity sandbox (ADR-0015): perform one on-behalf-of exchange for the caller and show both tokens' claims.

    Returns summaries only — never a raw token. The caller can only ever learn what Keycloak
    would issue to Maestro *for them*, which is information they are entitled to.
    """
    caller = await _caller(authorization)
    request = exchange_request(body.audience, body.scope)
    try:
        issued = await exchange_token(caller.raw_token, audience=body.audience, scope=body.scope)
    except TokenExchangeError as exc:
        return {"subject": caller.as_dict(), "request": request, "issued": None,
                "error": {"error": exc.error, "description": exc.description}}
    return {"subject": caller.as_dict(), "request": request, "issued": issued.summary(), "error": None}


async def health() -> dict[str, Any]:
    return {
        "model": settings.llm_model,
        "effort": settings.llm_effort,
        "skills": [f"{s.name}@{s.version}" for s in orchestrator.skills()],
        "fleet_gateway": settings.fleet_gateway_mcp_url,
        "auth_mode": settings.maestro_auth_mode,
    }


def create_app():
    orchestrator.init()
    return build_app(mcp, health=health, extra_routes=[Mount("/api", app=api)])
