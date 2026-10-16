# INFO fields that matter

`valkey_info(section)` returns the fields of that section. These are the ones to read and
how to interpret them.

## memory

| Field | Read it as |
| --- | --- |
| `used_memory` | bytes in use by data + overhead |
| `used_memory_human` | same, human |
| `used_memory_rss` | OS-resident size; compare with used for fragmentation |
| `maxmemory` | the limit (64 MB here = 67,108,864) |
| `maxmemory_policy` | `allkeys-lru` here: any key can be evicted |
| `mem_fragmentation_ratio` | rss/used; > 1.5 is fragmentation |
| `used_memory_peak` | high-water mark since start |

## stats

| Field | Read it as |
| --- | --- |
| `evicted_keys` | lifetime evictions (counter); use Prometheus for rate |
| `expired_keys` | TTL expirations (normal) |
| `keyspace_hits` / `keyspace_misses` | lifetime; ratio = hits/(hits+misses) |
| `rejected_connections` | `maxclients` reached |
| `total_commands_processed` | lifetime commands |
| `instantaneous_ops_per_sec` | current throughput |
| `total_net_input_bytes` | inbound bytes; a filler workload shows a jump |

## clients

| Field | Read it as |
| --- | --- |
| `connected_clients` | now |
| `blocked_clients` | in BLPOP etc. |
| `maxclients` | via `valkey_config("maxclients")` |

## keyspace

`db0:keys=12345,expires=12000,avg_ttl=58000` — keys with TTLs vs without. The portal's
`member:` keys have TTLs; a filler workload typically has `expires=0`.

## server

| Field | Read it as |
| --- | --- |
| `uptime_in_seconds` | small value = recent restart (cold cache) |
| `redis_version` / `valkey_version` | for the report |

## persistence

Not used for incident triage here (no persistence configured); mention only if a restart
happened and the cache came back empty.
