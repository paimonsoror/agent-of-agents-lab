# Adding a domain

Worked example: a **compute** domain (Kubernetes nodes and pods) — the next domain from
the reference sketch. The pattern is the six steps from `AGENTS.md`; nothing in Maestro
changes.

## 1. Write the skill (most of the work)

`skills/compute-observability/SKILL.md`:

```markdown
---
name: compute-observability
description: Domain cognition for the compute agent. Use when asked whether nodes, pods, scheduling, OOM kills, restarts, CPU or memory pressure, or the Kubernetes platform are involved in an incident. ...
metadata:
  domain: compute
  version: "1.0"
  owner: platform-compute
---
# Compute: Kubernetes
... tools, investigation order, deciding, recommended actions, evidence/links, Finding JSON ...
```

Metrics already exist in the shared Prometheus from kube-prometheus-stack:
`kube_pod_container_status_restarts_total`, `kube_pod_container_status_last_terminated_reason`,
`node_memory_MemAvailable_bytes`, `node_cpu_seconds_total`, `kube_node_status_condition`,
`kube_pod_status_phase`. Put the PromQL cookbook and failure-mode catalogue in
`references/`. Add panel ids for a `domain-compute` dashboard. Keep `SKILL.md` ≤ 500 lines.

## 2. Add the tool module

`agents/domain-agent/domains/compute.py` exposing read-only, platform-native tools via the
Kubernetes API (a namespaced or cluster-read Role): `list_unhealthy_pods(namespace)`,
`describe_node_pressure()`, `recent_oom_kills(minutes)`. Register them the way
`cache.py` does; the common loop, events, auth and Prometheus tools are inherited. The
skill tells the model when to use each tool.

## 3. Deploy the agent

`deploy/charts/maestro/templates/domain-compute/`: a Deployment of the same
`maestro/domain-agent` image with `AGENT_DOMAIN=compute`,
`AGENT_SKILLS=compute-observability,prometheus-observability`, a Service `compute-agent:8000`,
a ServiceMonitor (job label becomes `compute-agent`), the Role/RoleBinding for the
Kubernetes reads, and the `anthropic` Secret in namespace `domain-compute`. There is no
separate platform to deploy — the cluster itself is the platform.

## 4. Wire identity and the gateway

- `deploy/keycloak/realm.json`: add realm role `domain:compute`; grant it to
  `fleet-console`, `sre-lead`, and whichever humans should see it. For on-behalf-of
  delegation (ADR-0015) also add: a bearer-only client `compute-agent`; a client scope
  `domain-compute` with an audience mapper for `compute-agent`; a `scopeMappings` entry
  `{ "clientScope": "domain-compute", "roles": ["domain:compute"] }`; and `domain-compute`
  in the `maestro` client's `optionalClientScopes`. Maestro derives the audience and scope
  names from the domain id, so nothing in Maestro changes.
- the fleet gateway config (ConfigMap `fleet-gateway-config`, rendered from
  `deploy/charts/maestro/templates/gateway/fleet-gateway.yaml`): add target
  `compute → http://compute-agent.domain-compute:8000/mcp` to the `/agents/mcp` backend,
  the rule `mcp.tool.target == "compute" && "domain:compute" in jwt.realm_access.roles`, and
  `compute-agent` to the route's `jwtAuth.audiences`. The agent Deployment gets
  `OIDC_AUDIENCE=compute-agent,maestro-gateway` automatically from the chart helper.
- `deploy/grafana/domain-compute.json`: the dashboard with the panel ids your skill cites.

Maestro discovers `compute_assess` automatically on the next request; its orchestration
skill's triage matrix (`skills/maestro-orchestration/references/triage-matrix.md`) should
gain a row for compute symptoms.

## 5. Show it

`agents/fleet-console/static/topology.js`: add nodes `compute-agent` and `kubernetes` with
their edges to `gateway` and `prometheus`. The event kinds are unchanged.

## 6. Give it a fault, then record it

`deploy/scenarios/compute-oom.yaml`: a Deployment with a memory limit it exceeds, so
`OOMKilled` restarts appear. Add it to `scripts/scenario.sh` and the console's scenario
list. Then: `docs/adr/0014-compute-domain.md`, `make reset && make smoke`, and extend
`scripts/smoke.sh` to expect `compute_assess` for `sre-lead`.

## Checklist

- [ ] `SKILL.md` validates (`scripts/validate-skills.py`)
- [ ] agent answers `health()` through the gateway
- [ ] `engineer` without the role does not see `compute_*` tools
- [ ] `make obo-demo USER_ID=sre-lead DOMAIN=compute` issues a token with `aud: compute-agent` and only `domain:compute`
- [ ] dashboard uid/panels match the skill
- [ ] scenario applies and clears idempotently
- [ ] ADR written; `docs/contracts.md` updated (ports, env, job name)
