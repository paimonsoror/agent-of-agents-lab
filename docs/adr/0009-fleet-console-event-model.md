# 0009. The Fleet Console is an event hub fed by every component

Date: 2026-10-15
Status: Accepted

## Context

Executive leadership must *see* how a question flows through the ecosystem as it
happens. Gateway access logs and traces exist, but they are not legible to that
audience, and the interesting moments (skills loaded, evidence gathered, finding
returned) happen inside the agents.

## Decision

The Fleet Console (`agents/fleet-console`) is a small FastAPI service with:

- an **event hub**: `POST /api/events` from any component, an in-memory ring buffer,
  and `GET /api/stream` (SSE) to browsers;
- the **incident intake** (`Raise P1 incident` button, free-form questions) acting as
  the ServiceNow/Teams stand-in with its own Keycloak identity;
- **scenario controls** that apply/clear fault injection through the Kubernetes API;
- a **static single-page UI** (vanilla JS + SVG, no build step) that renders the
  topology from the reference sketch, animates edges on events, shows the timeline,
  and renders the assessment card. Playback controls let a presenter step through a
  completed trace.

Every first-party component emits events through `maestro_common.events` with the
trace id; emission is best-effort and never blocks the request path.

## Consequences

- The console is the only component that knows about all the others' *names*;
  the topology is data (`topology.js`), not code.
- Events are ephemeral (ring buffer); traces older than the buffer are gone. Fine
  for a demo; the design points at OpenTelemetry for durable traces.
- The console has a narrow Kubernetes Role in the domain namespaces for scenarios.

## Alternatives considered

- Deriving the animation from OpenTelemetry traces (agentgateway exports them) —
  accurate but misses in-agent moments; could feed the same hub later.
- A React build — unnecessary tooling on the VM; vanilla keeps `make up` simple.
