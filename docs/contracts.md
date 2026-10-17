# Contracts

The single place where names, ports, environment variables and schemas are agreed.
If you change anything here, change every consumer in the same commit.

## Cluster and namespaces

| Item | Value |
| --- | --- |
| KIND cluster name | `maestro` |
| Node image | `kindest/node:v1.37.0` (pinned in `deploy/versions.env`) |
| Namespaces | `maestro-identity`, `maestro-monitoring`, `maestro-gateway`, `maestro` (orchestrator + console), `domain-apim`, `domain-cache`, `domain-messaging`, `member-portal` |

## Host ports (KIND `extraPortMappings` → NodePort, listen on 0.0.0.0)

| Host port | Service | Namespace | Purpose |
| --- | --- | --- | --- |
| 30080 | `fleet-console:8080` | `maestro` | Fleet Console UI, event hub, scenario API |
| 30081 | `monitoring-grafana:80` | `maestro-monitoring` | Grafana (admin / `maestro-demo`) |
| 30082 | `keycloak:8080` | `maestro-identity` | Keycloak (admin / `maestro-demo`); **JWT issuer base URL** |
| 30083 | `fleet-gateway:80` → 4000 | `maestro-gateway` | agentgateway: `/agents/mcp`, `/maestro/mcp`, `/ui` |
| 30084 | `monitoring-kube-prometheus-prometheus:9090` | `maestro-monitoring` | Prometheus |
| 30085 | `edge-gateway:80` → 4000 | `domain-apim` | The member portal's public API (`/api/...`) |

`HOST_IP` is detected by `scripts/up.sh` (first non-loopback IPv4) and can be
overridden (`make up HOST_IP=...`). Public URLs are `http://$HOST_IP:<port>`.

## In-cluster service names

| Service (DNS) | Port | Notes |
| --- | --- | --- |
| `keycloak.maestro-identity` | 8080 | realm `maestro` |
| `monitoring-kube-prometheus-prometheus.maestro-monitoring` | 9090 | Prometheus HTTP API |
| `monitoring-grafana.maestro-monitoring` | 80 | |
| `fleet-gateway.maestro-gateway` | 80 | agentgateway (fleet) |
| `edge-gateway.domain-apim` | 80 | agentgateway (APIM platform) |
| `apim-agent.domain-apim` | 8000 | MCP at `/mcp`, `/healthz`, `/metrics` |
| `valkey.domain-cache` | 6379 | |
| `valkey-exporter.domain-cache` | 9121 | |
| `cache-agent.domain-cache` | 8000 | |
| `kafka.domain-messaging` | 9092 | KRaft single node |
| `kafka-exporter.domain-messaging` | 9308 | |
| `messaging-agent.domain-messaging` | 8000 | |
| `maestro.maestro` | 8000 | `POST /api/ask`, MCP at `/mcp`, `/healthz`, `/metrics` |
| `fleet-console.maestro` | 8080 | see API below |
| `portal-api.member-portal` | 8000 | sample app; `/metrics` |

## Identity (Keycloak realm `maestro`)

| Principal | Type | Credential | Realm roles |
| --- | --- | --- | --- |
| `fleet-console` | confidential client, service account | secret `fleet-console-secret` | `maestro:ask`, `domain:apim`, `domain:cache`, `domain:messaging` |
| `maestro` | confidential client, service account; **may perform standard token exchange** (ADR-0015) | secret `maestro-secret` | (none — Maestro never calls an agent as itself; it exchanges the caller's token) |
| `ide-cli` | public client, direct access grants | — | — |
| `apim-agent`, `cache-agent`, `messaging-agent` | bearer-only clients (audiences only) | — | — |
| user `engineer` | human | password `engineer` | `maestro:ask`, `domain:apim`, `domain:cache` (deliberately **not** messaging) |
| user `sre-lead` | human | password `sre-lead` | all four |

- `fleet-console` and `ide-cli` tokens carry `aud: [maestro-gateway, maestro]` (two audience
  mappers). Access token lifespan: 8 hours (demo convenience).
- Client scopes `domain-apim`, `domain-cache`, `domain-messaging` (optional on `maestro`): each
  adds `aud: <d>-agent` and permits realm role `domain:<d>` (scope mapping).

### On-behalf-of tokens (ADR-0015)

Maestro exchanges the caller's token before each agent call (RFC 8693 at the token endpoint):
`grant_type=urn:ietf:params:oauth:grant-type:token-exchange`, `client_id=maestro`,
`subject_token=<caller's token>`, `subject_token_type=urn:ietf:params:oauth:token-type:access_token`,
`requested_token_type=urn:ietf:params:oauth:token-type:access_token`, `audience=<d>-agent`,
`scope=domain-<d>`. The issued token has `sub` = the caller, `azp` = `maestro`,
`act: {"client_id": "maestro"}`, `aud` = `<d>-agent`, `realm_access.roles` = `["domain:<d>"]`,
lifetime 300 s. Keycloak refuses (`invalid_request`, "Requested audience not available: …")
when the caller lacks `domain:<d>`. Mode: `MAESTRO_AUTH_MODE=exchange|passthrough`, overridable
per request (`auth_mode`).
- Issuer (`iss`): `http://$HOST_IP:30082/realms/maestro`. Keycloak is started with
  `KC_HOSTNAME=http://$HOST_IP:30082` so tokens fetched via the in-cluster URL carry the
  same issuer.
- JWKS (in-cluster): `http://keycloak.maestro-identity:8080/realms/maestro/protocol/openid-connect/certs`
- Token endpoint (in-cluster): `http://keycloak.maestro-identity:8080/realms/maestro/protocol/openid-connect/token`

## Fleet gateway routes (agentgateway, `maestro-gateway`)

| Path | Backend | Policies |
| --- | --- | --- |
| `/agents/mcp` | MCP backend multiplexing targets `apim`, `cache`, `messaging` (→ `http://<x>-agent.domain-<x>:8000/mcp`) | `jwtAuth` strict, audiences `maestro-gateway, apim-agent, cache-agent, messaging-agent` (any one); `backendAuth.passthrough`; `mcpAuthorization`: `mcp.tool.target == "<x>" && "domain:<x>" in jwt.realm_access.roles` |
| `/agents/<x>/mcp` (one per domain) | MCP backend with the single target `<x>` → `http://<x>-agent.domain-<x>:8000/mcp` | `jwtAuth` strict, audiences `<x>-agent, maestro-gateway`; passthrough; rule `"domain:<x>" in jwt.realm_access.roles`. **Maestro calls agents here** (ADR-0015): an on-behalf-of token is addressed to one agent, and the multiplexed route would open sessions with all of them |
| `/maestro/mcp` | MCP target `maestro` → `http://maestro.maestro:8000/mcp` | `jwtAuth` strict, audiences `maestro-gateway, maestro`; passthrough; rule `"maestro:ask" in jwt.realm_access.roles` |
| `/ui` | built-in admin UI (read-only mode) | — |

Multiplexed tool names on `/agents/mcp` are prefixed by target: `apim_assess`, `cache_assess`,
`messaging_assess` (and `<x>_health`). The single-target routes `/agents/<x>/mcp` expose the
agent's own names, `assess` and `health`; Maestro strips the prefix when it calls through them.

## Environment variables

Common to every first-party Python service (`agents/common` reads these):

| Variable | Example | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | from Secret `anthropic` | LLM |
| `LLM_MODEL` | `claude-sonnet-5-5` (agents) / `claude-opus-5-5` (Maestro) | |
| `LLM_EFFORT` | `medium` (agents) / `high` (Maestro) | `output_config.effort` |
| `LLM_FALLBACKS` | `default` or empty | server-side refusal fallbacks |
| `FLEET_EVENTS_URL` | `http://fleet-console.maestro:8080/api/events` | event hub |
| `PROMETHEUS_URL` | `http://monitoring-kube-prometheus-prometheus.maestro-monitoring:9090` | |
| `GRAFANA_PUBLIC_URL` | `http://$HOST_IP:30081` | for deep links in evidence |
| `OIDC_ISSUER` | `http://$HOST_IP:30082/realms/maestro` | expected `iss` |
| `OIDC_JWKS_URL` | in-cluster JWKS URL | |
| `OIDC_TOKEN_URL` | in-cluster token URL | for services that mint or exchange tokens |
| `OIDC_AUDIENCE` | `cache-agent,maestro-gateway` | comma list; any one must appear in `aud`. Domain agents: `<name>,maestro-gateway`; Maestro: `maestro,maestro-gateway`; others: `maestro-gateway` |
| `SKILLS_DIR` | `/app/skills` | |
| `SERVICE_NAME` | `cache-agent` | event `source` and MCP server name |
| `LOG_LEVEL` | `info` | |

Domain agent (`agents/domain-agent`):

| Variable | Purpose |
| --- | --- |
| `AGENT_DOMAIN` | `apim` \| `cache` \| `messaging` — selects `domains/<domain>.py` |
| `AGENT_SKILLS` | comma list, e.g. `cache-observability,prometheus-observability` |
| `VALKEY_URL` | `redis://valkey.domain-cache:6379` (cache only) |
| `KAFKA_BOOTSTRAP` | `kafka.domain-messaging:9092` (messaging only) |
| `EDGE_GATEWAY_URL` | `http://edge-gateway.domain-apim` (apim only) |
| `EDGE_CONFIGMAP` | `domain-apim/edge-gateway-config` (apim only; read via the Kubernetes API with a namespaced Role) |

Maestro: `FLEET_GATEWAY_MCP_URL=http://fleet-gateway.maestro-gateway/agents/mcp` (discovery; calls
go to the per-agent route derived from it, `/agents/<x>/mcp`),
`AGENT_SKILLS=maestro-orchestration`, `OIDC_CLIENT_ID=maestro`, `OIDC_CLIENT_SECRET=maestro-secret`
(used only for token exchange), `MAESTRO_AUTH_MODE=exchange|passthrough` (chart value
`identity.delegation`).

Fleet Console: `MAESTRO_URL=http://maestro.maestro:8000`, `OIDC_CLIENT_ID=fleet-console`,
`OIDC_CLIENT_SECRET=fleet-console-secret`, `MAESTRO_AUTH_MODE` (for display), `PUBLIC_GRAFANA_URL`,
`PUBLIC_PROMETHEUS_URL`, `PUBLIC_KEYCLOAK_URL`, `PUBLIC_GATEWAY_URL`, `PUBLIC_EDGE_URL`.

## Maestro API (`maestro.maestro:8000`)

| Method & path | Body / result |
| --- | --- |
| `POST /api/ask` | bearer: caller's token. `{ "question", "trace_id"?, "auth_mode"? }` → Assessment. `auth_mode` ∈ `exchange` \| `passthrough` overrides `MAESTRO_AUTH_MODE` for this request |
| `POST /api/delegate` | bearer: caller's token. `{ "audience", "scope"? }` → `{ "subject": <token summary>, "request": {…}, "issued": <token summary> \| null, "error": { "error", "description" } \| null }`. Performs one real exchange; never returns raw tokens |
| `/mcp` | MCP: tool `ask_maestro(question)` (default mode) |

A *token summary* is `{ sub, username, azp, act, delegated, aud[], roles[], scope, iat, exp, lifetime_s, jti }`.

## Fleet Console API

| Method & path | Body / result |
| --- | --- |
| `POST /api/events` | one Event (below); fire-and-forget, 202 |
| `GET /api/stream` | SSE stream of Events (`event: fleet`, `data: <Event JSON>`), replays the last 200 on connect |
| `GET /api/events?trace_id=` | JSON array of Events |
| `POST /api/incident` | `{ "title", "service", "description", "auth_mode"? }` → `{ "trace_id" }`; starts a trace, emits `incident.raised`, asks Maestro asynchronously |
| `POST /api/ask` | `{ "question", "auth_mode"? }` → `{ "trace_id" }`; free-form question as the console identity |
| `POST /api/identity/try` | `{ "user": "engineer" \| "sre-lead" \| "fleet-console", "domain": "apim" \| "cache" \| "messaging" }` → Maestro's `/api/delegate` result plus `user`, `domain`, `audience`, `scope`. Real exchange, no trace, no raw tokens (ADR-0015) |
| `GET /api/assessment/{trace_id}` | the Assessment once posted, else 404 |
| `GET /api/scenarios` | `[{ "name", "title", "domain", "active" }]` |
| `POST /api/scenarios/{name}` / `DELETE /api/scenarios/{name}` | apply / clear a fault |
| `GET /api/topology` | nodes + edges for the UI, public URLs, demo `credentials`, and `identity: { delegation, modes[], domains[], agent_audiences[], obo_lifetime_s }` |
| `GET /healthz` | |

## Event schema

```json
{
  "ts": "2026-10-15T20:14:05.123Z",
  "trace_id": "trc-20261015-201405-7f3a",
  "source": "cache-agent",
  "kind": "evidence.gathered",
  "summary": "valkey_evicted_keys_total rose from 0 to 48k in 10m",
  "edge": { "from": "cache-agent", "to": "prometheus" },
  "detail": { "query": "rate(redis_evicted_keys_total[5m])", "result": "..." }
}
```

`kind` values: `incident.raised`, `question.asked`, `token.issued`, `token.exchanged`,
`token.refused`, `request.sent`, `request.received`, `tools.discovered`, `skills.loaded`,
`evidence.gathered`, `llm.turn`, `finding.returned`, `assessment.posted`,
`scenario.applied`, `scenario.cleared`, `error`.

- `token.exchanged` (source `maestro`, edge → `keycloak`): detail `{ request, subject, issued, target }`
  where `request` is the exchange request minus secrets, `subject`/`issued` are token summaries.
- `token.refused` (source `maestro`, edge → `keycloak`): detail `{ request, subject, error, error_description, target }`.
- `request.sent` from Maestro carries `detail.transport.auth` = `{ mode: "exchange"|"passthrough", scheme, …token summary }`
  and `detail.transport.agent_audience`.

Node ids for `edge.from` / `edge.to` and `source`: `console`, `ide`, `maestro`,
`gateway`, `keycloak`, `skills`, `apim-agent`, `cache-agent`, `messaging-agent`,
`edge-gateway`, `valkey`, `kafka`, `prometheus`, `grafana`, `portal`.

## Finding schema (returned by every `<domain>_assess` tool)

```json
{
  "domain": "cache",
  "agent": "cache-agent",
  "trace_id": "trc-...",
  "implicated": true,
  "confidence": 0.91,
  "headline": "Valkey is evicting under memory pressure",
  "summary": "…two or three sentences for a responder…",
  "evidence": [
    { "source": "prometheus", "query": "rate(redis_evicted_keys_total[5m])", "observation": "…", "link": "http://…grafana…" },
    { "source": "valkey", "query": "INFO memory", "observation": "used_memory 63.9MB of maxmemory 64MB" }
  ],
  "recommended_actions": ["Raise maxmemory or evict the filler keyspace", "…"],
  "skills_used": ["cache-observability", "prometheus-observability"],
  "caller": { "sub": "a6f0d810-…", "username": "service-account-fleet-console", "azp": "maestro",
              "act": "maestro", "delegated": true, "aud": ["cache-agent"], "roles": ["domain:cache"] }
}
```

`confidence` is 0–1. `implicated=false` with high confidence means "cleared". `caller` is
who the finding was produced for (`sub`, `username`) and who presented the token (`azp`,
`act`); `delegated=false` with `azp` = the caller's own client means passthrough.

## Assessment schema (Maestro)

```json
{
  "trace_id": "trc-...",
  "question": "P1: member portal API returning 503s",
  "verdict": "API management is implicated; cache and messaging are healthy.",
  "implicated": [{ "domain": "apim", "confidence": 0.82, "headline": "…" }],
  "cleared": [{ "domain": "cache", "confidence": 0.91, "headline": "…" }],
  "not_consulted": [{ "domain": "messaging", "reason": "caller lacks role domain:messaging" }],
  "next_step_for_human": "Roll back change CHG0123 on the edge gateway route /api/members.",
  "findings": [ "…full Finding objects…" ],
  "caller": { "sub": "…", "azp": "fleet-console", "username": "service-account-fleet-console" },
  "auth_mode": "exchange",
  "model": "claude-opus-5-5",
  "duration_ms": 41873
}
```

`not_consulted[].reason` is one of `caller lacks role domain:<d>` (hidden by the gateway),
`delegation refused by Keycloak: <description>` (ADR-0015) or `agent error: <message>`.

## Skills layout

```
skills/<name>/SKILL.md            frontmatter: name (== dir), description, metadata.domain, metadata.version
skills/<name>/references/*.md     loaded on demand through the agent's read_reference(skill, file) tool
```

Agents put the full `SKILL.md` body of each skill in `AGENT_SKILLS` into the system
prompt (cached) and list available references by filename.

## Images and build

- One Dockerfile per service at `agents/<service>/Dockerfile`, **build context = repo root**
  (`docker build -f agents/<service>/Dockerfile -t maestro/<service>:<tag> .`), based on
  `python:3.13-slim`. Each installs `agents/common` first, then its own
  `requirements.txt`, then copies `skills/` to `/app/skills`.
- Images: `maestro/domain-agent`, `maestro/maestro`, `maestro/fleet-console`,
  `maestro/member-portal` (one image; the Deployment's `command` selects
  `portal-api`, `portal-consumer` or `loadgen`).
- `scripts/build-images.sh` tags each image with the first 12 hex chars of the sha256
  of `agents/common + agents/<service> + skills` and runs `kind load docker-image`.
  Tags are passed to Helm as `images.<name>.tag`; `imagePullPolicy: IfNotPresent`.
- Pinned third-party images and chart versions live in `deploy/versions.env`.

## Helm layout

- Third-party: `kube-prometheus-stack` (release `monitoring`, ns `maestro-monitoring`)
  with values `deploy/values/kube-prometheus-stack.yaml`.
- First-party umbrella chart `deploy/charts/maestro`, release `maestro`, installed into
  ns `maestro`; it renders the Namespace objects and every other resource with an
  explicit `metadata.namespace`. Values: `hostIp`, `images.*`, `thirdParty.*` (from
  `versions.env`), `anthropicApiKey` (set at deploy time, never in a values file; the
  chart creates Secret `anthropic` in `maestro`, `domain-apim`, `domain-cache`,
  `domain-messaging`).
- **Both agentgateways are plain Deployments** in the umbrella chart (image
  `cr.agentgateway.dev/agentgateway:v1.6.0`, args `-f /config/config.yaml`), with their
  config in ConfigMaps `fleet-gateway-config` (ns `maestro-gateway`) and
  `edge-gateway-config` (ns `domain-apim`), key `config.yaml`, mounted as a directory at
  `/config` (never `subPath`, so the gateway's file watcher sees updates). Services
  expose `http` 80→4000 and `metrics` 15020.
- Every first-party service serves `/metrics` as an explicit route on its main port (never a
  sub-application mount: a trailing catch-all mount would swallow the bare path and 404).
- Prometheus `job` label == Service name (ServiceMonitors leave `jobLabel` unset):
  `fleet-gateway`, `edge-gateway`, `valkey-exporter`, `kafka-exporter`, `portal-api`,
  `portal-consumer`, `apim-agent`, `cache-agent`, `messaging-agent`, `maestro`.

## Domain agent tools (names are fixed; skills refer to them)

| Domain | Tool | Returns |
| --- | --- | --- |
| all | `query_prometheus(expr)` | instant query, compact table |
| all | `query_prometheus_range(expr, minutes)` | first/min/max/last per series |
| all | `read_reference(skill, file)` | a skill's reference file |
| all | `list_prometheus_targets()` | job/instance/health |
| apim | `get_edge_routes()` | the edge gateway's routes (name, match, backend) parsed from `edge-gateway-config` |
| apim | `get_edge_change_history()` | the ConfigMap's `maestro.io/*` annotations (change id, summary, who, when, last rollback) |
| apim | `probe_edge_route(path)` | status + latency of one `GET` through the edge gateway |
| cache | `valkey_info(section)` | `INFO <section>` parsed to a dict (`memory`, `stats`, `keyspace`, `clients`, `server`) |
| cache | `valkey_config(pattern)` | `CONFIG GET <pattern>` |
| cache | `valkey_slowlog(count)` | last N slowlog entries |
| cache | `valkey_sample_keys(count)` | key prefixes by `RANDOMKEY` sampling |
| messaging | `kafka_describe_topics()` | topics, partitions, leaders |
| messaging | `kafka_consumer_group_lag(group)` | per-partition lag, members, state |
| messaging | `kafka_broker_status()` | broker metadata |

Maestro tools: `<target>_assess` / `<target>_health` discovered from the gateway, plus
`read_reference`.

## Grafana dashboards (stable UIDs and panel ids; agents deep-link `/d/<uid>?viewPanel=<id>`)

| UID | Panels |
| --- | --- |
| `domain-apim` | 1 Edge request rate by status · 2 Edge 5xx ratio · 3 Edge p95 latency · 4 Requests by route · 5 Fleet gateway MCP calls |
| `domain-cache` | 1 Memory used vs max · 2 Evicted keys/s · 3 Keyspace hit ratio · 4 Commands/s · 5 Connected clients |
| `domain-messaging` | 1 Consumer group lag (portal-consumer) · 2 Messages produced/s · 3 Consumer group members · 4 Under-replicated partitions · 5 Brokers |
| `member-portal` | 1 Request rate by status · 2 p95 latency · 3 Cache hit ratio · 4 Events published/s |
| `maestro-fleet` | 1 Agent requests · 2 LLM tokens by service · 3 Tool calls by tool · 4 Gateway MCP calls · 5 Request duration p95 |

Key metric names (verified against exporter docs): agentgateway
`agentgateway_requests_total{gateway,listener,route,method,status}`,
`agentgateway_request_duration_seconds_bucket`, `agentgateway_mcp_requests_total`,
`agentgateway_config_synchronized`; redis_exporter `redis_memory_used_bytes`,
`redis_memory_max_bytes`, `redis_evicted_keys_total`, `redis_keyspace_hits_total`,
`redis_keyspace_misses_total`, `redis_commands_processed_total`,
`redis_connected_clients`, `redis_up`; kafka-exporter
`kafka_consumergroup_lag{consumergroup,topic,partition}`,
`kafka_consumergroup_members`, `kafka_topic_partition_current_offset`,
`kafka_topic_partition_under_replicated_partition`, `kafka_brokers`.

## Member portal metrics

`portal_http_requests_total{route,status}`, `portal_request_seconds_bucket{route}`,
`portal_cache_lookups_total{result="hit"|"miss"}`, `portal_events_published_total`,
`portal_consumer_events_consumed_total`. Topic: `member.events`; consumer group:
`portal-consumer`. Routes: `GET /api/members/{id}` (cached in Valkey, key
`member:<id>`, TTL 60 s; publishes an event), `GET /api/health`.

## Scenario mechanics (identical in `scripts/scenario.sh` and the console)

| Name | Apply | Clear | Active when |
| --- | --- | --- | --- |
| `apim-bad-route` | In ConfigMap `domain-apim/edge-gateway-config` replace `portal-api.member-portal` with `portal-api-v2.member-portal` in `config.yaml`; set annotations `maestro.io/change-id=CHG0123`, `maestro.io/change-summary=Route /api/members repointed to portal-api-v2 (canary)`, `maestro.io/changed-by=platform-apim-bot`, `maestro.io/changed-at=<RFC3339>` | reverse the replace; remove `change-id`; set `maestro.io/last-rollback=CHG0123`, `maestro.io/rolled-back-at=<RFC3339>` | annotation `maestro.io/change-id` present |
| `cache-pressure` | create Job `domain-cache/cache-filler` (image = Valkey) looping `valkey-benchmark -h valkey -t set -n 100000 -d 4096 -r 1000000 -q` every 5 s | delete `cache-filler`; run Job `cache-flush` (`valkey-cli -h valkey FLUSHALL`), delete it when complete | Job `cache-filler` exists |
| `messaging-lag` | scale `member-portal/deploy/portal-consumer` to 0 | scale to 1 | replicas == 0 |

Valkey runs with `--maxmemory 64mb --maxmemory-policy allkeys-lru`. `make up` clears all
scenarios explicitly (baseline on every build); otherwise `scenario clear` or the console.

## Demo credentials (public by design)

Exposed by `GET /api/topology` under `credentials` for the console's hover cards; sourced
from the chart's `demo:` values, which must stay in step with
`deploy/values/kube-prometheus-stack.yaml` (Grafana) and `deploy/keycloak/realm.json`.
