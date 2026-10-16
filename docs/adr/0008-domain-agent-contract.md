# 0008. Every domain agent exposes the same `assess` contract and recommends, never remediates

Date: 2026-10-15
Status: Accepted

## Context

Maestro must be able to add domains without learning new interfaces, and executives
must trust that the system cannot act on production unprompted.

## Decision

Every domain agent is an MCP server with exactly these tools:

- `assess(question: str, trace_id: str) -> Finding` — the only tool Maestro relies on.
  The agent runs its own LLM loop with domain tools and returns the Finding schema
  from `docs/contracts.md` (implicated, confidence, headline, summary, evidence,
  recommended_actions, skills_used, caller).
- `health() -> dict` — platform reachability and the agent's own status.

Agents are **read-only** against their platforms and against Prometheus. They
recommend actions; they do not take them. Remediation (rollback, scaling) is a human
decision, executed outside the agents. Fault-injection controls exist only in the
Fleet Console / Makefile and are never callable by an agent.

One image, `maestro/domain-agent`, serves every domain; `AGENT_DOMAIN` selects the
tool module. Shared behaviour (events, auth, skills, LLM loop, Prometheus) is in
`agents/common`.

## Consequences

- Adding a domain never changes Maestro.
- Confidence is a number the orchestrator can rank by; "cleared" is a first-class
  outcome, not silence.
- Agents cannot cause an incident during a demo.
- Richer per-domain tools can still be exposed through the gateway (the RBAC rules
  allow every tool on an authorised target), which is what the IDE path uses.

## Alternatives considered

- Free-text answers — unrankable, unparseable, un-demoable.
- Letting agents remediate behind an approval — a strong future ADR; out of scope.
