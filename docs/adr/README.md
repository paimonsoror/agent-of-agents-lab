# Architecture Decision Records

We record every significant decision as an ADR so that humans and AI agents who work
on this repository later can see *why* things are the way they are, not just *what*
they are. ADRs are immutable once accepted; to change a decision, write a new ADR that
supersedes the old one and link both ways.

## Index

| # | Title | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-kind-on-a-single-vm.md) | Run the whole ecosystem in KIND on a single VM | Accepted |
| [0003](0003-agentgateway-as-fleet-gateway.md) | agentgateway is the fleet (MCP/AI) gateway | Accepted |
| [0004](0004-mcp-with-jwt-today-a2a-north-star.md) | MCP with JWT propagation today; A2A is the north star | Accepted |
| [0005](0005-keycloak-identity-and-token-propagation.md) | Keycloak issues identities; callers' tokens are propagated, not re-minted | Accepted |
| [0006](0006-prometheus-grafana-shared-monitoring.md) | Prometheus + Grafana are the shared monitoring every domain sends to | Accepted |
| [0007](0007-skills-md-as-agent-cognition.md) | Agent cognition lives in agentskills.io `SKILL.md` bundles | Accepted |
| [0008](0008-domain-agent-contract.md) | Every domain agent exposes the same `assess` contract and recommends, never remediates | Accepted |
| [0009](0009-fleet-console-event-model.md) | The Fleet Console is an event hub fed by every component | Accepted |
| [0010](0010-claude-models-and-effort.md) | Claude Opus 5.5 orchestrates, Claude Sonnet 5.5 runs domain agents | Accepted |
| [0011](0011-fault-injection-scenarios.md) | Each domain ships a reversible fault scenario | Accepted |
| [0012](0012-idempotent-build.md) | One idempotent `make up`; one destructive `make down` | Accepted |
| [0013](0013-domain-platform-stand-ins.md) | Open-source stand-ins for the domain platforms | Accepted |

## Template

```markdown
# NNNN. Title

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by [NNNN](NNNN-slug.md)

## Context
What forces are at play; what we know; what constrains us.

## Decision
What we are doing, stated plainly.

## Consequences
What becomes easier, what becomes harder, what we must remember.

## Alternatives considered
Each with the reason it lost.
```
