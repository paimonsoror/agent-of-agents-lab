# PromQL cookbook for the Maestro fleet

Copy these; replace the job/label values as needed. All windows are 5m unless noted.

## Generic shapes

| Need | Expression |
| --- | --- |
| Request rate | `sum(rate(<metric>_total{job="X"}[5m]))` |
| Rate by a label | `sum by (status) (rate(<metric>_total{job="X"}[5m]))` |
| Error ratio | `sum(rate(<m>_total{job="X",status=~"5.."}[5m])) / clamp_min(sum(rate(<m>_total{job="X"}[5m])), 1e-9)` |
| p95 latency | `histogram_quantile(0.95, sum by (le) (rate(<m>_seconds_bucket{job="X"}[5m])))` |
| Increase over window | `sum(increase(<metric>_total{job="X"}[15m]))` |
| Gauge now | `max(<gauge>{job="X"})` |
| Did it change? | `query_prometheus_range("<expr>", 30)` and compare first vs last |
| Target up? | `up{job="X"}` (1 = scraped successfully) |

## Edge gateway (job="edge-gateway")

```promql
sum by (status) (rate(agentgateway_requests_total{job="edge-gateway"}[5m]))
sum(rate(agentgateway_requests_total{job="edge-gateway",status=~"5.."}[5m])) / clamp_min(sum(rate(agentgateway_requests_total{job="edge-gateway"}[5m])), 1e-9)
sum by (route, status) (rate(agentgateway_requests_total{job="edge-gateway"}[5m]))
histogram_quantile(0.95, sum by (le) (rate(agentgateway_request_duration_seconds_bucket{job="edge-gateway"}[5m])))
max(agentgateway_config_synchronized{job="edge-gateway"})
```

## Fleet gateway (job="fleet-gateway")

```promql
sum by (status) (rate(agentgateway_requests_total{job="fleet-gateway"}[5m]))
sum(rate(agentgateway_mcp_requests_total{job="fleet-gateway"}[5m]))
```

## Valkey (job="valkey-exporter")

```promql
max(redis_memory_used_bytes{job="valkey-exporter"}) / max(redis_memory_max_bytes{job="valkey-exporter"})
sum(rate(redis_evicted_keys_total{job="valkey-exporter"}[5m]))
sum(rate(redis_keyspace_hits_total{job="valkey-exporter"}[5m])) / clamp_min(sum(rate(redis_keyspace_hits_total{job="valkey-exporter"}[5m])) + sum(rate(redis_keyspace_misses_total{job="valkey-exporter"}[5m])), 1e-9)
sum(rate(redis_commands_processed_total{job="valkey-exporter"}[5m]))
max(redis_connected_clients{job="valkey-exporter"})
sum by (db) (redis_db_keys{job="valkey-exporter"})
max(redis_up{job="valkey-exporter"})
```

## Kafka (job="kafka-exporter")

```promql
sum(kafka_consumergroup_lag{job="kafka-exporter",consumergroup="portal-consumer"})
sum by (topic) (kafka_consumergroup_lag{job="kafka-exporter",consumergroup="portal-consumer"})
max(kafka_consumergroup_members{job="kafka-exporter",consumergroup="portal-consumer"})
sum(rate(kafka_topic_partition_current_offset{job="kafka-exporter",topic="member.events"}[5m]))
sum(kafka_topic_partition_under_replicated_partition{job="kafka-exporter"})
max(kafka_brokers{job="kafka-exporter"})
sum by (topic) (kafka_topic_partitions{job="kafka-exporter"})
```

## Member portal (job="portal-api" / "portal-consumer")

```promql
sum by (status) (rate(portal_http_requests_total{job="portal-api"}[5m]))
histogram_quantile(0.95, sum by (le) (rate(portal_request_seconds_bucket{job="portal-api"}[5m])))
sum(rate(portal_cache_lookups_total{job="portal-api",result="hit"}[5m])) / clamp_min(sum(rate(portal_cache_lookups_total{job="portal-api"}[5m])), 1e-9)
sum(rate(portal_events_published_total{job="portal-api"}[5m]))
sum(rate(portal_consumer_events_consumed_total{job="portal-consumer"}[5m]))
```

## Agents (job = agent service name)

```promql
sum by (service) (rate(maestro_requests_total[5m]))
sum by (service, kind) (rate(maestro_llm_tokens_total[5m]))
sum by (service, tool) (rate(maestro_tool_calls_total[5m]))
```

## Pitfalls

- `rate()` on a gauge is meaningless; `deriv()` or a range first/last comparison instead.
- A counter reset (pod restart) shows as a dip in `rate()`; mention restarts if you see `up` flap.
- `histogram_quantile` needs `le` preserved in the `sum by`.
- If you see `+Inf` from `histogram_quantile`, the request fell outside the highest bucket — report "p95 above the largest bucket (Xs)".
