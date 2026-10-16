# Guidance for agents working in this repository

You are extending a reference architecture that is demoed to executives across many
labs. Repeatability and clarity beat cleverness. Read this file, then
`docs/architecture.md`, then `docs/contracts.md`, then the ADR index in `docs/adr/`.

## Non-negotiables

1. **Idempotent build.** `make up` must converge from any state (fresh VM, half-built
   cluster, previous successful build). `make down` must leave nothing behind except
   Docker images. Never write a step that only works the first time.
2. **No secrets in the repo.** The only secret is `ANTHROPIC_API_KEY`, read at deploy
   time from `~/.maestro/secrets.env` on the build host. Demo passwords for Keycloak,
   Grafana and the realm's clients are intentionally public and documented.
3. **Every decision gets an ADR.** New component, new transport, new model, changed
   port, changed schema → add `docs/adr/NNNN-slug.md` using the template in
   `docs/adr/README.md`. Supersede rather than edit accepted ADRs.
4. **Contracts are the source of truth.** Service names, ports, env vars, event and
   finding schemas live in `docs/contracts.md`. Change the doc *and* every consumer in
   the same change.
5. **The orchestrator is called Maestro.** Do not introduce other names for it.
6. **Agent cognition lives in `skills/`, not in prompts.** If an agent needs to know
   something about a domain, write it into the domain's `SKILL.md` or a file under its
   `references/`. The Python code should stay domain-agnostic plumbing.
7. **Pinned versions.** Every image tag, chart version and Python dependency is pinned
   in one place (`deploy/versions.env`, `agents/*/requirements.txt`). Bump
   deliberately and note it in the commit message.

## Layout

```
agents/
  common/            maestro_common package: skills loader, events, auth, LLM loop, prometheus client
  domain-agent/      one image, parameterised by AGENT_DOMAIN; domain tools in domains/<domain>.py
  maestro/           orchestrator: HTTP API for the console + MCP server for IDEs
  fleet-console/     event hub (SSE) + static single-page UI + scenario controls
  member-portal/     sample app: portal-api, portal-consumer, loadgen
deploy/
  kind/              cluster config (fixed NodePort → host port mappings)
  charts/maestro/    our Helm umbrella chart (all first-party components + Keycloak/Valkey/Kafka)
  values/            values for third-party charts (kube-prometheus-stack, agentgateway ×2)
  grafana/           provisioned dashboards, one per domain + fleet overview
  keycloak/          realm export (clients, roles, users)
  scenarios/         fault-injection manifests
scripts/             up.sh, down.sh, build-images.sh, smoke.sh, scenario.sh, remote.sh
skills/              SKILL.md bundles; one directory per skill, agentskills.io format
docs/                architecture, contracts, ADRs, runbook, demo script
site/                GitHub Pages tour: static HTML/CSS/JS, no build step (ADR-0014); keep in step with docs/
```

## Adding a domain (the intended extension path)

1. Write `skills/<domain>-observability/SKILL.md` (+ `references/`). This is most of
   the work and the most valuable part.
2. Add `agents/domain-agent/domains/<domain>.py` exposing the platform-native tools.
3. Add the platform + exporter + agent Deployment to `deploy/charts/maestro/templates/domain-<domain>/`.
4. Add a target to the fleet gateway's MCP backend and an authorization rule
   (`deploy/values/agentgateway-fleet.yaml`), a realm role `domain:<domain>`
   (`deploy/keycloak/realm.json`), and a Grafana dashboard.
5. Add the node to the Fleet Console topology (`agents/fleet-console/static/topology.js`).
6. Add a fault scenario. Record it all in an ADR. Run `make reset && make smoke`.

`docs/adding-a-domain.md` walks through this with the messaging domain as the example.

## Working style

- Run everything through the Makefile; do not hand-run kubectl in a way the scripts
  don't reproduce.
- Prefer boring technology: plain Deployments, Helm, bash with `set -euo pipefail`,
  vanilla JS for the console. No build steps that need Node on the VM.
- When something is uncertain (chart value, API shape), test it on the VM and record
  the verified shape in the relevant doc.
- Keep `SKILL.md` under 500 lines; push detail into `references/`.
