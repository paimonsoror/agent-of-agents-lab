"""How Maestro reaches remote agents. The ONLY file that knows the transport (ADR-0004)
and the delegation mode (ADR-0015).

Today: MCP over Streamable HTTP through the fleet gateway. The bearer token on each call is,
by default, an **on-behalf-of token**: Maestro exchanges the caller's token at Keycloak
(RFC 8693) for one addressed to the single agent it is about to call, carrying only that
domain's role, valid for minutes. `MAESTRO_AUTH_MODE=passthrough` restores the pre-ADR-0015
behaviour (the caller's own token, forwarded unchanged) for side-by-side comparison.
Swapping to A2A means replacing discover()/call() here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from maestro_common import settings
from maestro_common.auth import Caller, TokenExchangeError, exchange_request, exchange_token
from maestro_common.events import current_trace, emit

KNOWN_DOMAINS: tuple[str, ...] = ("apim", "cache", "messaging")
AUTH_MODES: tuple[str, ...] = ("exchange", "passthrough")


class DelegationRefused(RuntimeError):
    """Keycloak would not issue an on-behalf-of token for this caller and target."""

    def __init__(self, target: str, audience: str, description: str) -> None:
        super().__init__(f"delegation refused for {audience}: {description}")
        self.target = target
        self.audience = audience
        self.description = description


@dataclass(frozen=True)
class RemoteTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    target: str  # the gateway target prefix, i.e. the domain id

    @property
    def is_assess(self) -> bool:
        return self.name.endswith("_assess")


def _http(token: str) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(30.0, read=600.0),
    )


async def discover(token: str) -> tuple[list[RemoteTool], list[str]]:
    """List the tools the gateway exposes to this caller; return (tools, domains not visible).

    Discovery always uses the caller's own token: the gateway's answer is "what may this person see",
    which is exactly the question. Delegation happens per call, in `call()`.
    """
    async with _http(token) as http:
        async with Client(streamable_http_client(settings.fleet_gateway_mcp_url, http_client=http)) as client:
            result = await client.list_tools()
    tools = [
        RemoteTool(name=t.name, description=t.description or "", input_schema=t.input_schema or {}, target=t.name.split("_", 1)[0])
        for t in result.tools
    ]
    visible = sorted({t.target for t in tools if t.target in KNOWN_DOMAINS})
    not_visible = [d for d in KNOWN_DOMAINS if d not in visible]
    emit(
        "tools.discovered",
        f"Gateway exposes {len(tools)} tools; visible domains: {', '.join(visible) or 'none'}; hidden: {', '.join(not_visible) or 'none'}",
        to="gateway",
        detail={"tools": [t.name for t in tools], "visible": visible, "not_visible": not_visible, "hidden": not_visible},
    )
    return tools, not_visible


def _root_cause(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{exc.__class__.__name__}: {exc}"[:300]


async def _token_for(caller: Caller, target: str, mode: str) -> tuple[str, dict[str, Any]]:
    """The bearer token to present for `target`, plus a description of it for the console."""
    if mode != "exchange":
        return caller.raw_token, {
            "mode": "passthrough",
            "scheme": "Bearer JWT (caller's own token, passed through unchanged)",
            **caller.as_dict(),
        }
    audience, scope = f"{target}-agent", f"domain-{target}"
    request = exchange_request(audience, scope)
    subject = caller.as_dict()
    try:
        issued = await exchange_token(caller.raw_token, audience=audience, scope=scope)
    except TokenExchangeError as exc:
        emit(
            "token.refused",
            f"Keycloak refused to delegate {caller.display} to {audience}: {exc.description}",
            to="keycloak",
            detail={"request": request, "subject": subject, "error": exc.error, "error_description": exc.description, "target": target},
        )
        raise DelegationRefused(target, audience, exc.description) from exc
    summary = issued.summary()
    emit(
        "token.exchanged",
        f"Keycloak issued an on-behalf-of token for {audience}: sub={caller.display}, azp=maestro, roles={summary['roles']}, "
        f"expires in {summary['lifetime_s']}s",
        to="keycloak",
        detail={"request": request, "subject": subject, "issued": summary, "target": target},
    )
    return issued.token, {
        "mode": "exchange",
        "scheme": "Bearer JWT (on-behalf-of token from Keycloak standard token exchange, RFC 8693)",
        **summary,
    }


def agent_mcp_url(target: str) -> str:
    """The gateway route for one agent (`/agents/<target>/mcp`, docs/contracts.md).

    Calls go through a single-target route because an on-behalf-of token is addressed to exactly one
    agent; the multiplexed `/agents/mcp` route (used for discovery) would open a session with every
    agent, and the others would rightly refuse the token.
    """
    base = settings.fleet_gateway_mcp_url
    return base.replace("/agents/mcp", f"/agents/{target}/mcp") if "/agents/mcp" in base else base


async def call(caller: Caller, tool_name: str, args: dict[str, Any], *, mode: str = "exchange") -> Any:
    """Invoke one remote tool through the gateway and return its structured result (or text)."""
    target, _, bare_name = tool_name.partition("_")
    # The multiplexed discovery route prefixes tool names with the target ("cache_assess"); the
    # single-target route Maestro calls through exposes the agent's own names ("assess").
    remote_name = bare_name or tool_name
    token, auth = await _token_for(caller, target, mode)
    endpoint = agent_mcp_url(target)
    emit(
        "request.sent",
        f"Maestro → {tool_name}",
        to="gateway",
        detail={
            "tool": tool_name,
            "remote_tool": remote_name,
            "args": args,
            # How this hop is made — surfaced in the console's play-by-play for the gateway (ADR-0004/0005/0015).
            "transport": {
                "protocol": "MCP tools/call over Streamable HTTP",
                "endpoint": endpoint,
                "gateway_target": target,
                "gateway_rule": f'mcp.tool.target == "{target}" && "domain:{target}" in jwt.realm_access.roles',
                "agent_audience": f"{target}-agent",
                "auth": auth,
                "trace_id": current_trace.get(),
            },
        },
    )
    try:
        async with _http(token) as http:
            async with Client(streamable_http_client(endpoint, http_client=http)) as client:
                result = await client.call_tool(remote_name, args)
    except BaseExceptionGroup as group:  # anyio task groups wrap transport errors; surface the real cause
        raise RuntimeError(f"{tool_name} via gateway: {_root_cause(group)}") from group
    text = "\n".join(b.text for b in result.content if isinstance(b, TextContent))
    if result.is_error:
        raise RuntimeError(text or f"{tool_name} returned an error")
    structured = result.structured_content
    if isinstance(structured, dict):
        if set(structured) == {"result"}:
            return structured["result"]
        return structured
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
