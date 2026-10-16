# 0004. MCP with JWT propagation today; A2A is the north star

Date: 2026-10-15
Status: Accepted

## Context

Agent-to-agent (A2A) is the protocol we expect enterprise agent ecosystems to converge
on: agent cards, task lifecycles, streaming. But A2A in an enterprise means every
agent is a first-class principal with its own identity, discovery and trust
relationships — a non-human-identity (NHI) management problem that most
organisations have not solved. MCP, by contrast, is a client/server tool protocol:
the orchestrator is the only "agent" from the identity system's point of view and
the domain agents look like tool servers behind a gateway.

## Decision

Maestro talks to domain agents over **MCP (Streamable HTTP)** through the fleet
gateway, and the **caller's JWT is propagated** on every hop. Domain agents are MCP
servers that expose an `assess` tool. The protocol-specific surface is isolated:

- domain agents are built with the MCP Python SDK's `MCPServer` and could be wrapped by
  an A2A agent card without changing their reasoning code;
- Maestro's "federation" step is a thin adapter (`agents/maestro/federation.py`) that
  discovers and calls remote agents — the only file that changes for A2A;
- the gateway already supports `a2a: {}` routes with the same `jwtAuth` policy.

The migration path to A2A is: add agent cards to the domain agents, add an A2A route
per agent on the gateway, swap the federation adapter. Identity stays in Keycloak.

## Consequences

- Today's identity story is simple and auditable: one IdP, one token format, one
  enforcement point, end-to-end authorisation per caller.
- Domain agents cannot initiate conversations with each other; Maestro is the hub.
  That is the intended control point for a first deployment.
- Long-running A2A task semantics (progress, cancellation) are approximated with
  MCP's request/response plus the console's event stream.

## Alternatives considered

- A2A now — would require NHI per agent, agent-card discovery and trust fan-out
  before the first demo; the point of this project is to avoid that complexity.
- Plain HTTP/JSON between services — loses tool discovery, the gateway's
  MCP-native authorisation, and the IDE integration for free.
