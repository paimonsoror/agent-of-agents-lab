# Fleet metrics catalog

What each scrape target exposes, which metrics the domain skills rely on, and the labels
you can group by. Metric names are those emitted by the pinned exporter versions.

## agentgateway (jobs `edge-gateway`, `fleet-gateway`) — port 15020

| Metric | Type | Key labels | Meaning |
| --- | --- | --- | --- |
| `agentgateway_requests_total` | counter | `gateway`, `listener`, `route`, `method`, `status` | HTTP requests handled |
| `agentgateway_request_duration_seconds` | histogram | same + `le` | end-to-end request duration |
| `agentgateway_request_processing_seconds` | histogram | | time from receipt to upstream call |
| `agentgateway_upstream_call_duration_seconds` | histogram | | outbound call duration |
| `agentgateway_retries_total` | counter | | retries to upstream |
| `agentgateway_mcp_requests_total` | counter | | MCP JSON-RPC requests (fleet gateway) |
| `agentgateway_config_synchronized` | gauge | | 1 when the on-disk config loaded cleanly; 0 after a bad reload |
| `agentgateway_downstream_connections_total` | counter | | inbound connections |

Status `503` with route present usually means "no healthy upstream". Status `404` means
no route matched. `agentgateway_config_synchronized == 0` means a config edit failed to
apply and the gateway is still running the previous config.

## redis_exporter (job `valkey-exporter`) — port 9121

| Metric | Type | Meaning |
| --- | --- | --- |
| `redis_up` | gauge | exporter can reach Valkey |
| `redis_memory_used_bytes` | gauge | `used_memory` from `INFO memory` |
| `redis_memory_max_bytes` | gauge | `maxmemory` (0 means unlimited) |
| `redis_evicted_keys_total` | counter | keys evicted under `maxmemory` policy |
| `redis_expired_keys_total` | counter | keys expired by TTL (normal, not a fault) |
| `redis_keyspace_hits_total` / `redis_keyspace_misses_total` | counter | key lookups |
| `redis_commands_processed_total` | counter | command throughput |
| `redis_commands_total{cmd}` | counter | per-command counts |
| `redis_connected_clients` | gauge | client connections |
| `redis_blocked_clients` | gauge | clients in blocking ops |
| `redis_db_keys{db}` | gauge | keys per database |
| `redis_rejected_connections_total` | counter | `maxclients` hit |
| `redis_slowlog_length` | gauge | entries in SLOWLOG |

## kafka-exporter (job `kafka-exporter`) — port 9308

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `kafka_brokers` | gauge | | brokers in the cluster (expect 1 here) |
| `kafka_topic_partitions{topic}` | gauge | | partitions per topic |
| `kafka_topic_partition_current_offset{topic,partition}` | gauge | | log end offset (rate = produce rate) |
| `kafka_topic_partition_oldest_offset` | gauge | | |
| `kafka_topic_partition_under_replicated_partition` | gauge | | 1 if under-replicated |
| `kafka_topic_partition_leader_is_preferred` | gauge | | |
| `kafka_consumergroup_current_offset{consumergroup,topic,partition}` | gauge | | committed offset |
| `kafka_consumergroup_lag{consumergroup,topic,partition}` | gauge | | log end − committed |
| `kafka_consumergroup_members{consumergroup}` | gauge | | live members; 0 = nobody consuming |

Lag is a gauge: never `rate()` it. Use range first/last to show growth.

## member portal (jobs `portal-api`, `portal-consumer`)

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `portal_http_requests_total` | counter | `route`, `status` | API requests served |
| `portal_request_seconds` | histogram | `route` | latency |
| `portal_cache_lookups_total` | counter | `result` = `hit` \| `miss` \| `error` | Valkey lookups |
| `portal_events_published_total` | counter | | messages produced to `member.events` |
| `portal_consumer_events_consumed_total` | counter | | messages consumed (consumer only) |

## agents (jobs `apim-agent`, `cache-agent`, `messaging-agent`, `maestro`)

| Metric | Labels | Meaning |
| --- | --- | --- |
| `maestro_requests_total` | `service`, `operation`, `outcome` | inbound assess/health calls |
| `maestro_request_seconds` | `service`, `operation` | duration histogram |
| `maestro_llm_turns_total` | `service`, `model` | model calls |
| `maestro_llm_tokens_total` | `service`, `model`, `kind` | tokens by kind |
| `maestro_tool_calls_total` | `service`, `tool`, `outcome` | tool calls inside the loop |

## Grafana dashboards (uid → panels)

| uid | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| `domain-apim` | Edge request rate by status | Edge 5xx ratio | Edge p95 latency | Requests by route | Fleet gateway MCP tool calls |
| `domain-cache` | Memory used vs max | Evicted keys/s | Keyspace hit ratio | Commands/s | Connected clients |
| `domain-messaging` | Consumer group lag (portal-consumer) | Messages produced/s | Consumer group members | Under-replicated partitions | Brokers |
| `member-portal` | Request rate by status | p95 latency | Cache hit ratio | Events published/s | — |
| `maestro-fleet` | Agent requests | LLM tokens by service | Tool calls by tool | Gateway MCP calls | Request duration p95 |
