# 0003. agentgateway is the fleet (MCP/AI) gateway

Date: 2026-10-15
Status: Accepted

## Context

The design needs an open-source API/AI gateway with real MCP capabilities: it must
terminate MCP, validate JWTs, authorise per tool, and ideally speak A2A for the
north-star migration. The reference sketch showed Kong.

Verified on 2026-10-15:

- **Kong Gateway**: the MCP plugins (`ai-mcp-proxy`, `ai-mcp-oauth2`) require a Kong AI
  / Enterprise license from Gateway 3.12 onward; there is no OSS build of them. Kong
  OSS could only proxy MCP as opaque HTTP.
- **Apache APISIX**: its `mcp-bridge` plugin is officially deprecated.
- **agentgateway** (Linux Foundation / Agentic AI Foundation, Rust): purpose-built for
  MCP, A2A and LLM traffic; `jwtAuth`, `mcpAuthorization` (CEL rules over `jwt.*`
  claims and `mcp.tool.name`/`mcp.tool.target`), MCP multiplexing of many servers
  behind one endpoint, `backendAuth.passthrough`, Prometheus metrics on `:15020`,
  OpenTelemetry tracing, a built-in admin UI, and a Helm chart. It is also the data
  plane of kgateway (CNCF), so the Kubernetes-Gateway-API path exists.

## Decision

agentgateway v1.6.0 is the **fleet gateway**. It exposes one multiplexed MCP endpoint
(`/agents/mcp`) for all domain agents and one for Maestro (`/maestro/mcp`). A second
instance is the **edge gateway** of the API-management domain, fronting the member
portal — so the APIM domain's "platform" is itself a real gateway with declarative,
inspectable config.

Both instances are deployed as plain Deployments from our umbrella chart (image
`cr.agentgateway.dev/agentgateway:v1.6.0`, `-f /config/config.yaml`) rather than via
the vendor's `agentgateway-standalone` chart. The reason is operational: each
gateway's whole configuration is one ConfigMap (`fleet-gateway-config`,
`edge-gateway-config`) that the APIM agent reads as "the platform's declarative
config and change history" and that the fault scenario patches with change
annotations. The vendor chart remains the right choice for a real deployment and is
referenced in `docs/runbook.md`.

## Consequences

- Tool-level RBAC by JWT role is a one-line CEL rule per domain; the gateway filters
  `tools/list`, so unauthorised agents are invisible, not merely blocked.
- Adding a domain is adding a target and a rule; clients never change.
- A2A migration is a policy change on the same gateway (ADR-0004).
- Gateway metrics land in the shared Prometheus like any other platform.
- The product in the sketch (Kong) is replaced; the role it plays is unchanged.

## Alternatives considered

- Kong OSS — MCP would be nominal (opaque proxying); the "MCP-aware gateway" story
  would be false.
- kgateway + agentgateway via Gateway API CRDs — same data plane, more moving parts
  for no demo gain. Documented as the enterprise-scale option.
- IBM ContextForge MCP Gateway — MCP-only; no A2A path, heavier footprint.
