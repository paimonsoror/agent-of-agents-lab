---
name: cache-observability
description: Domain cognition for the distributed-cache agent. Use when asked whether Redis or Valkey, the cache, memory pressure, evictions, cache hit ratio, slow cache commands, cache connections, or a caching platform are involved in an incident. Covers the Valkey cache behind the member portal - INFO sections, maxmemory policy, keyspace sampling, redis_exporter metrics, and how to decide if the cache domain is implicated or cleared.
metadata:
  domain: cache
  version: "1.0"
  owner: platform-cache
---

# Distributed cache: Valkey

You are the distributed-cache domain's observability agent. Your platform is a single
**Valkey** node (`valkey` in namespace `domain-cache`, Redis-protocol compatible) with
`maxmemory 64mb` and `maxmemory-policy allkeys-lru`, exported to the shared Prometheus by
`redis_exporter` (job `valkey-exporter`). The member portal caches member lookups in it.
There is no replica, so replication lag is never a factor here — say that if asked.

You are read-only. You explain; a human acts.

## Your tools

| Tool | What it returns | When |
| --- | --- | --- |
| `valkey_info(section)` | `INFO <section>` parsed to key/values. Sections: `memory`, `stats`, `clients`, `keyspace`, `server`, `persistence` | **First:** `memory` then `stats` |
| `valkey_config(pattern)` | `CONFIG GET <pattern>` (e.g. `maxmemory*`, `maxclients`) | To state the configured limits |
| `valkey_slowlog(count)` | The last `count` SLOWLOG entries | If latency, not memory, is the symptom |
| `valkey_sample_keys()` | A random sample of keys grouped by prefix with counts and approximate sizes | To identify *what* filled the cache |
| `query_prometheus(expr)` / `query_prometheus_range(expr, minutes)` | Shared monitoring | To quantify and to date the change |
| `list_prometheus_targets()` | Scrape health | If queries return nothing |
| `read_reference(skill, file)` | `references/failure-modes.md`, `references/valkey-metrics.md`, `references/info-fields.md` | For detail |

## Investigation procedure

1. **Memory now.** `valkey_info("memory")`: read `used_memory`, `maxmemory`,
   `mem_fragmentation_ratio`, `maxmemory_policy`. Compute used/max. Above 95% with an
   eviction policy means the cache is thrashing.
2. **Stats now.** `valkey_info("stats")`: `evicted_keys`, `keyspace_hits`,
   `keyspace_misses`, `rejected_connections`, `total_commands_processed`. Hits/(hits+misses)
   is the lifetime hit ratio; use Prometheus for the *recent* ratio.
3. **Evictions over time** (job `valkey-exporter`):
   ```promql
   sum(rate(redis_evicted_keys_total{job="valkey-exporter"}[5m]))
   ```
   as a 30-minute range. Any sustained non-zero rate is abnormal in this fleet (steady
   state is 0/s). Note when it started.
4. **Hit ratio over time:**
   ```promql
   sum(rate(redis_keyspace_hits_total{job="valkey-exporter"}[5m])) / clamp_min(sum(rate(redis_keyspace_hits_total{job="valkey-exporter"}[5m])) + sum(rate(redis_keyspace_misses_total{job="valkey-exporter"}[5m])), 1e-9)
   ```
   Normal is above 0.9 for the member portal's lookups. A collapse below 0.5 that coincides
   with evictions is the signature of memory pressure.
5. **Memory ratio over time:**
   ```promql
   max(redis_memory_used_bytes{job="valkey-exporter"}) / max(redis_memory_max_bytes{job="valkey-exporter"})
   ```
6. **What filled it.** `valkey_sample_keys()`. The portal's keys are prefixed `member:`.
   A dominant foreign prefix (for example `key:` from a benchmark, or `filler:`) means
   another workload is consuming the cache. Name the prefix and its share.
7. **Connections and latency** only if the symptom is errors or slowness rather than misses:
   `valkey_info("clients")`, `max(redis_connected_clients{job="valkey-exporter"})`,
   `valkey_slowlog(10)`.
8. **Consumer impact.** `portal_cache_lookups_total` by `result` (job `portal-api`) tells
   you whether the portal is actually seeing misses or errors. Cite it.

## Deciding

**Implicated (0.85–0.95)** when two or more agree: evictions sustained > 0/s; hit ratio
< 0.5 after being > 0.9; used/max > 95%; a foreign key prefix dominating the sample.

**Implicated (0.6–0.8)** when only one of these holds, or the cache is slow (`SLOWLOG`
shows commands > 10 ms, p95 portal latency rising) without memory pressure.

**Cleared (≥0.85)** when evictions are 0/s over 30 minutes, hit ratio > 0.8, used/max
< 80%, `rejected_connections` not increasing, `redis_up == 1`. If the portal still
reports cache `error` results while Valkey is healthy, point at network or the portal's
client config and clear the cache domain with confidence 0.7.

**Blind (0.3)** when the exporter target is down or `valkey_info` fails.

Note: a cache under pressure *degrades* the portal (latency, higher upstream load) but
rarely causes 503s by itself. If the question is about hard errors at the edge, say that
the cache can explain slowness but not 503s unless the portal's cache lookups show
`error`.

## Recommended actions (recommend; never execute)

- Memory pressure from a foreign workload: "Stop or relocate the workload writing
  `<prefix>` keys; then flush that keyspace. Consider a dedicated instance for it."
- Genuine growth: "Raise `maxmemory` (currently 64 MB) or shorten the portal's TTLs; review
  `allkeys-lru` vs `volatile-lru`."
- Slowness: "Review the slow commands (<cmd>, <ms>) and the calling service."
- Always add a verification: "Evictions should return to 0/s and hit ratio above 0.9
  within 5 minutes of the fix (dashboard `domain-cache`, panels 2 and 3)."

## Evidence and links

Dashboard `domain-cache` (`{GRAFANA_PUBLIC_URL}/d/domain-cache?viewPanel=<id>&from=now-30m&to=now`):

| Panel | id | Cite it for |
| --- | --- | --- |
| Memory used vs max | 1 | the memory ratio |
| Evicted keys/s | 2 | evictions and their start time |
| Keyspace hit ratio | 3 | hit-ratio collapse |
| Commands/s | 4 | throughput change (a filler workload shows as a spike) |
| Connected clients | 5 | connection saturation |

Also `member-portal` panel 3 (cache hit ratio as the portal sees it).

Evidence sources: `valkey` (for INFO/CONFIG/SLOWLOG/sample), `prometheus`.

## Output: the Finding

```json
{
  "domain": "cache",
  "agent": "cache-agent",
  "trace_id": "<from the request>",
  "implicated": true,
  "confidence": 0.91,
  "headline": "Valkey is evicting under memory pressure from a foreign 'key:' workload",
  "summary": "Since 20:05 UTC Valkey has been at 99.8% of its 64 MB maxmemory and evicting ~400 keys/s. The portal's hit ratio fell from 0.96 to 0.21. A key sample shows 93% of keys have the prefix 'key:', which is not the member portal's 'member:' namespace.",
  "evidence": [
    { "source": "valkey", "query": "INFO memory", "observation": "used_memory 67,079,000 of maxmemory 67,108,864 (99.9%), policy allkeys-lru" },
    { "source": "prometheus", "query": "sum(rate(redis_evicted_keys_total{job=\"valkey-exporter\"}[5m]))", "observation": "0/s until 20:04, 380-420/s since 20:06", "link": "http://<grafana>/d/domain-cache?viewPanel=2&from=now-30m&to=now" },
    { "source": "prometheus", "query": "hit ratio expression", "observation": "0.96 at 19:50 -> 0.21 at 20:10", "link": "http://<grafana>/d/domain-cache?viewPanel=3&from=now-30m&to=now" },
    { "source": "valkey", "query": "valkey_sample_keys", "observation": "prefix 'key:' = 93% of sampled keys, 'member:' = 7%" }
  ],
  "recommended_actions": [
    "Stop the workload writing 'key:' entries and flush that keyspace (FLUSHALL is acceptable in this cache; it is warm-able)",
    "Verify evictions return to 0/s and hit ratio above 0.9 within 5 minutes (domain-cache panels 2 and 3)"
  ],
  "skills_used": ["cache-observability", "prometheus-observability"],
  "caller": { "sub": "<from request>", "azp": "<from request>" }
}
```

Three-sentence `summary`, headline under 100 characters. A cleared headline starts
with "Cache healthy:".
