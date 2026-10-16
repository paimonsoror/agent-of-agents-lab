"""How Maestro reaches remote agents. The ONLY file that knows the transport (ADR-0004).

Today: MCP over Streamable HTTP through the fleet gateway, with the caller's JWT
propagated as the bearer token. Swapping to A2A means replacing discover()/call() here.
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
from maestro_common.events import current_caller, current_trace, emit

KNOWN_DOMAINS: tuple[str, ...] = ("apim", "cache", "messaging")


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
    """List the tools the gateway exposes to this caller; return (tools, domains not visible)."""
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


async def call(token: str, tool_name: str, args: dict[str, Any]) -> Any:
    """Invoke one remote tool through the gateway and return its structured result (or text)."""
    target = tool_name.split("_", 1)[0]
    emit(
        "request.sent",
        f"Maestro → {tool_name}",
        to="gateway",
        detail={
            "tool": tool_name,
            "args": args,
            # How this hop is made — surfaced in the console's play-by-play for the gateway (ADR-0004/0005).
            "transport": {
                "protocol": "MCP tools/call over Streamable HTTP",
                "endpoint": settings.fleet_gateway_mcp_url,
                "gateway_target": target,
                "gateway_rule": f'mcp.tool.target == "{target}" && "domain:{target}" in jwt.realm_access.roles',
                "auth": {"scheme": "Bearer JWT (caller's token, passed through unchanged)", **current_caller.get()},
                "trace_id": current_trace.get(),
            },
        },
    )
    try:
        async with _http(token) as http:
            async with Client(streamable_http_client(settings.fleet_gateway_mcp_url, http_client=http)) as client:
                result = await client.call_tool(tool_name, args)
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
