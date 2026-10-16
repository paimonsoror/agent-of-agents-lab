# 0006. Prometheus + Grafana are the shared monitoring every domain sends to

Date: 2026-10-15
Status: Accepted

## Context

The architecture assumes a central monitoring tool that all domains already feed
(Dynatrace, Splunk, Datadog in the sketch). Domain agents must have expert knowledge
of what to look for in it, not just of their own platform.

## Decision

`kube-prometheus-stack` provides Prometheus and Grafana in `maestro-monitoring`.
Every platform exports natively (redis_exporter, kafka-exporter, both agentgateways'
`/metrics`, the member portal, and the agents themselves). Grafana is provisioned from
`deploy/grafana/` with one dashboard per domain and a fleet overview; dashboards have
stable UIDs so agents can deep-link to panels.

Domain agents query Prometheus through a shared tool (`query_prometheus`) and carry
their monitoring expertise in two skills: the shared `prometheus-observability` skill
(query hygiene, rate windows, label conventions) and the domain skill, which lists
the exact metrics, thresholds and dashboard panels for that platform.

## Consequences

- "Expert knowledge of the monitoring tool" is explicit, reviewable text in
  `skills/`, not implicit in a prompt.
- Findings cite Grafana panels by URL; responders open what the agent saw.
- Alertmanager is disabled and retention is 2 h to fit the RAM budget.
- `*SelectorNilUsesHelmValues=false` so ServiceMonitors from our chart are discovered.

## Alternatives considered

- OpenSearch / SigNoz / VictoriaMetrics — all viable; Prometheus is what every chosen
  platform exports to without adapters, and Grafana is the lingua franca.
- Loki for logs — valuable, deferred to keep the footprint down; the agents' design
  leaves room for a `query_logs` tool.
