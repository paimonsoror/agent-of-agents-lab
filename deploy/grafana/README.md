# Grafana dashboards

Provisioned into the shared Grafana (kube-prometheus-stack) by the umbrella chart. Every
dashboard has a **stable `uid`** and **stable panel ids** so the domain agents can deep-link
to exactly what they looked at: `${GRAFANA_PUBLIC_URL}/d/<uid>?viewPanel=<panel id>`.
The skills under `skills/` describe how to read each panel. All queries use the datasource
`{ "type": "prometheus", "uid": "prometheus" }`, which is the uid kube-prometheus-stack gives
its default Prometheus datasource. Job labels equal the Kubernetes service names
(`edge-gateway`, `fleet-gateway`, `valkey-exporter`, `kafka-exporter`, `portal-api`,
`portal-consumer`); agent metrics carry a `service` label.

| uid | Panel ids → titles |
| --- | --- |
| `domain-apim` | 1 Edge request rate by status · 2 Edge 5xx ratio (red > 5 %) · 3 Edge p95 latency · 4 Requests by route · 5 Fleet gateway MCP tool calls |
| `domain-cache` | 1 Memory used vs max (red > 90 %) · 2 Evicted keys/s · 3 Keyspace hit ratio (red < 50 %) · 4 Commands/s · 5 Connected clients |
| `domain-messaging` | 1 Consumer group lag (portal-consumer) (red > 500) · 2 Messages produced/s · 3 Consumer group members · 4 Under-replicated partitions · 5 Brokers |
| `member-portal` | 1 Request rate by status · 2 p95 latency · 3 Cache hit ratio (red < 50 %) · 4 Events published/s |
| `maestro-fleet` | 1 Agent requests · 2 LLM tokens by service · 3 Tool calls by tool · 4 Gateway MCP calls · 5 Request duration p95 |

Layout convention: two columns, every panel 12 wide × 8 high, 30-minute window, 10 s
refresh, tag `maestro`. Changing a panel id or uid is a contract change (`docs/contracts.md`)
because the skills reference them.
