# Valkey metrics via redis_exporter — exact queries

Job `valkey-exporter`, port 9121, scraped every 15 s. Metric names keep the `redis_`
prefix because the exporter is protocol-level.

## Memory

```promql
max(redis_memory_used_bytes{job="valkey-exporter"})
max(redis_memory_max_bytes{job="valkey-exporter"})
max(redis_memory_used_bytes{job="valkey-exporter"}) / max(redis_memory_max_bytes{job="valkey-exporter"})
max(redis_mem_fragmentation_ratio{job="valkey-exporter"})
```

## Evictions and expirations

```promql
sum(rate(redis_evicted_keys_total{job="valkey-exporter"}[5m]))     # abnormal if > 0 sustained
sum(rate(redis_expired_keys_total{job="valkey-exporter"}[5m]))     # normal TTL churn
```

## Hit ratio

```promql
sum(rate(redis_keyspace_hits_total{job="valkey-exporter"}[5m]))
  / clamp_min(
      sum(rate(redis_keyspace_hits_total{job="valkey-exporter"}[5m]))
    + sum(rate(redis_keyspace_misses_total{job="valkey-exporter"}[5m])), 1e-9)
```

## Throughput, clients, keys

```promql
sum(rate(redis_commands_processed_total{job="valkey-exporter"}[5m]))
sum by (cmd) (rate(redis_commands_total{job="valkey-exporter"}[5m]))
max(redis_connected_clients{job="valkey-exporter"})
sum(rate(redis_rejected_connections_total{job="valkey-exporter"}[5m]))
sum by (db) (redis_db_keys{job="valkey-exporter"})
max(redis_up{job="valkey-exporter"})
```

## As the portal sees it (job `portal-api`)

```promql
sum by (result) (rate(portal_cache_lookups_total{job="portal-api"}[5m]))
sum(rate(portal_cache_lookups_total{job="portal-api",result="hit"}[5m]))
  / clamp_min(sum(rate(portal_cache_lookups_total{job="portal-api"}[5m])), 1e-9)
histogram_quantile(0.95, sum by (le) (rate(portal_request_seconds_bucket{job="portal-api"}[5m])))
```

## Reading a range result

`query_prometheus_range(expr, 30)` returns `first/min/max/last`. For evictions: `first=0,
last=400` = started inside the window; `first=400, last=400` = already bad 30 minutes ago
(widen to 120 to find the start). For hit ratio: quote first and last as percentages.
