# Demo script — ten minutes with Maestro

Audience: executive leadership. Goal: show that one question to Maestro replaces the
first hour of a P1, that the system is governed by real identity, and that every domain
team keeps ownership of its own agent.

Before the session: `make up` finished, `make smoke` green, `make scenario-clear` run,
`make urls` printed. Open the Fleet Console (`http://<HOST_IP>:30080`) full screen and
Grafana (`:30081`) in a second tab. Keep a terminal with the repo ready.

## 0:00 — The picture (1 min)

Point at the topology on the console. Left: consumers — the incident intake (standing in
for ServiceNow / Teams) and an engineer in an IDE. Centre: **Maestro**, the conductor.
The vertical bar: the **fleet gateway** — every call between agents passes through it
with a verified identity. Right: three **domain agents**, each owning one platform
(API management, cache, messaging), all reading the same **shared monitoring**.

Say: "Nothing on this screen is a mock. Every box is running."

## 1:00 — Healthy baseline (1 min)

Press **Ask Maestro** with "Is the member portal healthy?". Watch the flow: console →
Maestro → gateway → three agents in parallel → Prometheus. The assessment card returns
three cleared domains. Click one evidence link; Grafana opens on the exact panel the
agent read.

Say: "Cleared is a real answer. Each agent had to prove its platform is fine."

## 2:00 — Something breaks (1 min)

In the console's **Scenarios** panel, apply **apim-bad-route**. Narrate: "A platform
engineer just pushed change CHG0123 to the edge gateway. It repoints the members route
at a canary that doesn't exist." After ~60 s the edge-gateway status panel in the console
turns red and Grafana's `domain-apim` 5xx ratio climbs.

## 3:00 — Raise the P1 (3 min)

Press **Raise P1 incident** ("Member portal API returning 503s"). Narrate the animation
as it happens:

1. **Token issued** — the console gets its own identity from Keycloak (non-human
   identity, no shared secrets between agents).
2. **Maestro receives** the incident, loads its orchestration skill.
3. **Tools discovered** — Maestro asks the gateway what it may call; the gateway answers
   with the three domain agents because the console's identity holds all three roles.
4. **Fan-out** — three edges light up at once. Each agent: *skills loaded* (the domain's
   `SKILL.md` — written by that domain's team), then *evidence gathered* against its
   platform and against Prometheus.
5. **Findings returned** — apim implicated 0.8+, cache and messaging cleared.
6. **Assessment posted** — one verdict, one next step: "Roll back CHG0123."

Open the assessment card. Read the next step aloud. Click the apim evidence link.

Say: "Minutes, not hours. And it told the responder exactly which change to roll back —
the agent read the change record itself."

## 6:00 — Same agents, in the IDE (2 min)

Switch to the terminal with Claude Code connected (see `docs/ide-setup.md`, logged in as
`engineer`). Ask: "Is the member portal healthy right now?" The console animates the same
flow, but from the **IDE** node, and the messaging agent stays grey.

Point at the assessment: `not_consulted: messaging — caller lacks role domain:messaging`.

Say: "The engineer's own identity travelled all the way down. The gateway never showed
them an agent they aren't entitled to. Same agents, same tools, governed per person."

## 8:00 — Clear it (30 s)

Clear the scenario in the console. Optionally re-ask; watch apim come back cleared with
`last-rollback: CHG0123` in its evidence.

## 8:30 — Talking points for Q&A (1.5 min)

- **Identity.** One IdP (Keycloak standing in for Entra/Okta). Every agent and service is
  a non-human identity. Tokens are propagated, never re-minted, so Maestro cannot escalate
  on anyone's behalf. The gateway enforces tool-level RBAC from JWT roles. ADR-0005.
- **Why MCP now, A2A later.** MCP keeps identity to one place while the NHI story
  matures. The gateway already speaks A2A; migration is a policy change and one adapter
  file. ADR-0004.
- **Domain ownership.** The cognition is a Markdown skill per domain (`skills/`). The
  cache team improves the cache agent with a pull request. No central AI team bottleneck.
  ADR-0007.
- **Adding a domain** (compute, network): a skill, a tool module, a gateway target, a role,
  a dashboard. `docs/adding-a-domain.md`. No change to Maestro.
- **Shared monitoring.** Prometheus/Grafana here; Dynatrace/Splunk in production. Agents
  carry expert knowledge of *what to look at* in that tool and cite the exact panel.
- **Safety.** Agents are read-only. They recommend; humans act. ADR-0008.
- **Repeatability.** `make down && make up` rebuilds everything identically in any lab.

## If something goes wrong

- Agents slow (> 2 min): the Anthropic API is the long pole; show the timeline while
  waiting, or replay the last trace with the console's playback controls.
- No animation: check `make smoke`; the event hub is the console itself — restart its
  pod (`kubectl -n maestro rollout restart deploy/fleet-console`).
- Scenario not visible in Grafana after 90 s: the gateway reloads the ConfigMap within
  about a minute; `make scenario-apim-bad-route` re-applies idempotently.
- Fall back to the recorded trace: the console keeps the last 200 events; use playback.
