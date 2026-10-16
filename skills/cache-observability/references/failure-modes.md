# Cache failure modes (Valkey / Redis)

## 1. Memory pressure and eviction storm

- **Looks like:** `used_memory` pinned at `maxmemory`; `evicted_keys` rising every second;
  hit ratio collapsing; the portal's p95 latency rising as it falls through to its
  database on every miss.
- **Confirm:** `valkey_info("memory")` + evictions rate + hit-ratio range; `valkey_sample_keys()`
  to name the offending prefix.
- **Cause patterns:** a foreign workload (benchmark, batch job, mis-pointed service) writing
  into the shared instance; TTLs removed; a key-size regression.
- **Recommend:** stop the writer, flush its keyspace, consider isolation. Confidence 0.85–0.95.

## 2. Hit ratio collapse without evictions

- **Looks like:** misses up, evictions 0, memory well under max.
- **Causes:** a deploy changed the portal's key format (new keys never hit); a FLUSH; a
  TTL set too short; a cold restart (`uptime_in_seconds` small in `INFO server`).
- **Confirm:** `redis_db_keys` dropped sharply (flush/restart) or stayed flat while misses
  rose (key-format change).
- **Recommend:** portal team to check key naming/TTL; cache cleared with 0.7 unless a
  restart occurred (then implicate with 0.6 and say "cache restarted at <time>").

## 3. Slow commands

- **Looks like:** portal latency up, hit ratio fine, `SLOWLOG` has entries > 10 ms,
  commands like `KEYS`, `SMEMBERS` on big sets, `FLUSHALL`.
- **Confirm:** `valkey_slowlog(10)`; `redis_commands_total{cmd="keys"}` rate.
- **Recommend:** remove the offending command pattern; use `SCAN`. Confidence 0.6–0.8.

## 4. Connection saturation

- **Looks like:** `rejected_connections` increasing; `connected_clients` near `maxclients`;
  the portal reports cache `error` results.
- **Confirm:** `valkey_info("clients")`, `valkey_config("maxclients")`,
  `rate(redis_rejected_connections_total[5m])`.
- **Recommend:** find the leaking client; raise `maxclients` as a stopgap. Confidence 0.8.

## 5. Instance down

- **Looks like:** `redis_up == 0`, exporter target up; portal cache lookups all `error`.
- **Confirm:** `valkey_info` fails; `up{job="valkey-exporter"}`.
- **Recommend:** restart/inspect the `valkey` Deployment. Confidence 0.95.

## 6. Fragmentation

- **Looks like:** `mem_fragmentation_ratio` > 1.5 with RSS far above used memory.
- **Confirm:** `INFO memory`.
- **Recommend:** `activedefrag`, restart in a window. Rarely an incident cause; mention
  only if nothing else explains memory.

## Thresholds

| Signal | Normal | Degraded | Severe |
| --- | --- | --- | --- |
| used/max | < 70% | 70–95% | > 95% |
| evictions/s | 0 | 1–50 | > 50 |
| hit ratio (5m) | > 0.9 | 0.5–0.9 | < 0.5 |
| rejected connections | 0 | any | sustained |
| SLOWLOG entry | < 1 ms | 1–10 ms | > 10 ms |
| fragmentation ratio | 1.0–1.3 | 1.3–1.5 | > 1.5 |
