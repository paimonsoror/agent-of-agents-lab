"""Maestro: HTTP API for the Fleet Console (/api/ask) and an MCP server for IDEs (/mcp), one process on :8000."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel
from starlette.routing import Mount

import orchestrator
from maestro_common import settings
from maestro_common.auth import JWTError, KeycloakTokenVerifier, auth_settings, caller_from_access_token, verify_bearer
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


api = FastAPI(title="Maestro API", docs_url=None, redoc_url=None)


@api.post("/ask")
async def ask(body: AskBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        caller = await asyncio.to_thread(verify_bearer, authorization)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    return await orchestrator.run_assessment(body.question.strip(), body.trace_id or new_trace_id(), caller)


async def health() -> dict[str, Any]:
    return {
        "model": settings.llm_model,
        "effort": settings.llm_effort,
        "skills": [f"{s.name}@{s.version}" for s in orchestrator.skills()],
        "fleet_gateway": settings.fleet_gateway_mcp_url,
    }


def create_app():
    orchestrator.init()
    return build_app(mcp, health=health, extra_routes=[Mount("/api", app=api)])
