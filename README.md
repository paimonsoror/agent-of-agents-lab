# Maestro — an Agent of Agents for Observability

Maestro is an opinionated reference architecture for enterprise observability in a
world of many distinct technology domains. Each domain (API management, distributed
cache, messaging, …) owns a **domain observability agent** that knows its platform
*and* knows exactly what to look for in the shared monitoring stack. **Maestro** is
the central conductor: a consumer (an incident, an engineer in an IDE) asks one
question, Maestro federates it to the domain agents that are relevant, and posts one
consolidated assessment. A human decides the next step.

Everything runs end-to-end on a single VM inside a KIND cluster, with open-source
stand-ins for the commercial platforms an enterprise would have, and it builds and
tears down identically every time (`make up` / `make down`).

```
 consumers            orchestration        fleet gateway         domain agents         domain platforms      shared monitoring
 ─────────            ─────────────        ─────────────         ─────────────         ────────────────      ─────────────────
 Fleet Console ──┐                        ┌──────────┐          apim-agent ─────────── edge gateway  ┐
 (incident btn)  ├──▶  Maestro  ──────▶   │ agent-   │ ──JWT──▶ cache-agent ────────── Valkey        ├──▶ Prometheus ◀── Grafana
 Engineer in IDE ┘   (Claude Opus 5.5)    │ gateway  │          messaging-agent ────── Kafka         ┘
                                          │ authn/z  │
                                          └──────────┘
                                               ▲ Keycloak (JWT issuer, non-human identities)
```

## What it demonstrates

| Capability | How it is shown |
| --- | --- |
| Federated, domain-scoped cognition | Each agent is driven by a `SKILL.md` bundle ([agentskills.io](https://agentskills.io)) for its domain plus a shared Prometheus skill |
| Agent-to-agent transport with real identity | MCP over an open-source AI gateway ([agentgateway](https://agentgateway.dev)); every hop carries a Keycloak-issued JWT; the gateway filters tools by the caller's roles |
| A2A as the north star | The same gateway speaks A2A; the migration is a routing-policy change, documented in [ADR-0004](docs/adr/0004-mcp-with-jwt-today-a2a-north-star.md) |
| Shared monitoring every domain already has | Prometheus + Grafana; all platforms export natively; agents query PromQL and deep-link to dashboards |
| Executive-grade visibility | The Fleet Console animates each request as it flows through the ecosystem, live |
| Same agents, same tools, in the IDE | Maestro and the domain agents are reachable from Claude Code / Copilot / Cursor through the gateway |
| Repeatable labs | One command builds the whole stack from nothing; one command removes it |

## Quick start

Prerequisites on the build host (a Linux VM, 8+ cores, 12+ GiB RAM, Docker): `docker`,
`kind`, `kubectl`, `helm`, `make`, `jq`, `python3`. `scripts/bootstrap-host.sh` installs
the missing ones.

```bash
# 1. put your Anthropic key where the build expects it (never in the repo)
mkdir -p ~/.maestro && chmod 700 ~/.maestro
echo 'ANTHROPIC_API_KEY=sk-ant-...' > ~/.maestro/secrets.env && chmod 600 ~/.maestro/secrets.env

# 2. build everything (idempotent — re-run any time, it converges)
make up

# 3. open the Fleet Console and press "Raise P1 incident"
make urls
```

From a workstation you can drive a remote VM instead: `make remote-up VM=user@host SSH_KEY=~/.ssh/key`.

`make down` deletes the cluster. `make reset` is down + up. `make smoke` proves the
stack is healthy. `make scenario-<name>` injects a fault for the agents to find
(see [docs/demo-script.md](docs/demo-script.md)).

## Repository map

| Path | What lives there |
| --- | --- |
| `docs/architecture.md` | The design, with diagrams. Start here. |
| `docs/contracts.md` | Every name, port, environment variable and JSON schema the components agree on |
| `docs/adr/` | Architecture Decision Records — the *why* behind every choice, for humans and agents |
| `docs/demo-script.md` | The executive walkthrough, minute by minute |
| `docs/runbook.md` | Operating it: secrets, URLs, troubleshooting, teardown |
| `skills/` | The `SKILL.md` bundles that give each agent its domain cognition |
| `agents/` | Python services: the domain agents, Maestro, the Fleet Console, the sample member portal |
| `deploy/` | KIND config, Helm chart, third-party Helm values, fault-injection scenarios |
| `scripts/` | The idempotent build/teardown/smoke scripts the Makefile calls |
| `AGENTS.md` | Conventions for AI agents (and humans) extending this repository |

## Naming

The orchestrator is **Maestro**. The namespace prefix, cluster name and Helm release
prefix are `maestro`. Domain agents are named `<domain>-agent`. The sample business
application whose incident we investigate is the **member portal**.
