"""Starlette application factory for every first-party MCP service.

Mounts the MCP Streamable HTTP app at /mcp (so the in-cluster URL is http://<svc>:8000/mcp),
plus /healthz and /metrics. DNS-rebinding protection is disabled because the gateway in
front already controls the Host header (per MCP SDK deployment guidance).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from maestro_common.config import settings

HealthCheck = Callable[[], Any]


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_app(mcp: MCPServer, *, health: HealthCheck | None = None, extra_routes: list[Any] | None = None) -> Starlette:
    mcp_app = mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def healthz(_: Request) -> JSONResponse:
        payload: dict[str, Any] = {"service": settings.service_name, "status": "ok"}
        if health:
            try:
                extra = health()
                if hasattr(extra, "__await__"):
                    extra = await extra
                payload.update(extra or {})
            except Exception as exc:  # noqa: BLE001
                return JSONResponse({"service": settings.service_name, "status": "degraded", "error": str(exc)}, status_code=503)
        return JSONResponse(payload)

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    async def metrics(_: Request) -> Response:
        # An explicit Route, not a Mount: the trailing MCP Mount("/") would swallow the bare /metrics path.
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    routes = [Route("/healthz", healthz), Route("/metrics", metrics)]
    routes += extra_routes or []
    routes.append(Mount("/", app=mcp_app))  # provides /mcp; must be last
    return Starlette(routes=routes, lifespan=lifespan)


def serve(app: Starlette, port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port, log_level=settings.log_level.lower(), proxy_headers=True)
