"""Environment-driven settings. Names and defaults are the contract in docs/contracts.md."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    service_name: str = field(default_factory=lambda: _env("SERVICE_NAME", "maestro-service"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "info"))

    # LLM
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "claude-sonnet-5-5"))
    llm_effort: str = field(default_factory=lambda: _env("LLM_EFFORT", "medium"))
    llm_fallbacks: str = field(default_factory=lambda: _env("LLM_FALLBACKS", "default"))
    llm_max_turns: int = field(default_factory=lambda: int(_env("LLM_MAX_TURNS", "12")))

    # Fleet console event hub
    fleet_events_url: str = field(default_factory=lambda: _env("FLEET_EVENTS_URL"))

    # Shared monitoring
    prometheus_url: str = field(default_factory=lambda: _env("PROMETHEUS_URL"))
    grafana_public_url: str = field(default_factory=lambda: _env("GRAFANA_PUBLIC_URL"))

    # Identity
    oidc_issuer: str = field(default_factory=lambda: _env("OIDC_ISSUER"))
    oidc_jwks_url: str = field(default_factory=lambda: _env("OIDC_JWKS_URL"))
    oidc_token_url: str = field(default_factory=lambda: _env("OIDC_TOKEN_URL"))
    # Comma-separated list of audiences this service accepts in `aud` (any one suffices). A domain
    # agent accepts its own client id (on-behalf-of tokens) and the gateway audience (direct callers).
    oidc_audience: str = field(default_factory=lambda: _env("OIDC_AUDIENCE", "maestro-gateway"))
    oidc_client_id: str = field(default_factory=lambda: _env("OIDC_CLIENT_ID"))
    oidc_client_secret: str = field(default_factory=lambda: _env("OIDC_CLIENT_SECRET"))
    # Maestro only: "exchange" (on-behalf-of tokens via RFC 8693, ADR-0015) or "passthrough" (ADR-0005).
    maestro_auth_mode: str = field(default_factory=lambda: _env("MAESTRO_AUTH_MODE", "exchange"))

    # Skills
    skills_dir: str = field(default_factory=lambda: _env("SKILLS_DIR", "/app/skills"))
    agent_skills: tuple[str, ...] = field(
        default_factory=lambda: tuple(s for s in _env("AGENT_SKILLS").split(",") if s)
    )

    # Domain agent specifics (unused by other services)
    agent_domain: str = field(default_factory=lambda: _env("AGENT_DOMAIN"))
    valkey_url: str = field(default_factory=lambda: _env("VALKEY_URL"))
    kafka_bootstrap: str = field(default_factory=lambda: _env("KAFKA_BOOTSTRAP"))
    edge_gateway_url: str = field(default_factory=lambda: _env("EDGE_GATEWAY_URL"))
    edge_configmap: str = field(default_factory=lambda: _env("EDGE_CONFIGMAP"))

    # Maestro specifics
    fleet_gateway_mcp_url: str = field(default_factory=lambda: _env("FLEET_GATEWAY_MCP_URL"))

    # Public URLs for links shown to humans
    public_grafana_url: str = field(default_factory=lambda: _env("PUBLIC_GRAFANA_URL"))
    public_prometheus_url: str = field(default_factory=lambda: _env("PUBLIC_PROMETHEUS_URL"))
    public_keycloak_url: str = field(default_factory=lambda: _env("PUBLIC_KEYCLOAK_URL"))
    public_gateway_url: str = field(default_factory=lambda: _env("PUBLIC_GATEWAY_URL"))
    public_edge_url: str = field(default_factory=lambda: _env("PUBLIC_EDGE_URL"))

    @property
    def oidc_audiences(self) -> tuple[str, ...]:
        return tuple(a.strip() for a in self.oidc_audience.split(",") if a.strip())


settings = Settings()
