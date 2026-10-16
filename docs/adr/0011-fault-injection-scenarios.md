# 0011. Each domain ships a reversible fault scenario

Date: 2026-10-15
Status: Accepted

## Context

A healthy system makes for a dull demo. The agents must have something real to find,
and the demo must show both an implicated and a cleared domain. Scenarios must be
reversible so `make reset` is never required between runs.

## Decision

Three scenarios, each implemented as a small, reversible change executed by
`scripts/scenario.sh` and by the Fleet Console (`POST/DELETE /api/scenarios/{name}`):

| Name | Apply | Clear | Signal |
| --- | --- | --- | --- |
| `apim-bad-route` | Patch the edge gateway ConfigMap: route `/api/members` → non-existent backend; annotate `maestro.io/change-id=CHG0123`, `maestro.io/changed-at`, `maestro.io/change-summary` | Restore the route; annotate `maestro.io/last-rollback=CHG0123` | `agentgateway_requests_total{status=~"5.."}` on the edge gateway; change annotations on the route |
| `cache-pressure` | Run Job `cache-filler` that writes well past `maxmemory` (Valkey runs with `maxmemory 64mb`, `allkeys-lru`) | Delete the job; `FLUSHDB` the filler keyspace via a one-shot Job | `redis_evicted_keys_total`, keyspace hit ratio, `used_memory` |
| `messaging-lag` | Scale `portal-consumer` to 0 | Scale to 1 | `kafka_consumergroup_lag` for group `portal-consumer` |

The member portal's load generator runs continuously so every metric has a baseline.
A scenario's "active" state is derived from the cluster (annotation present, job
exists, replicas == 0), never stored, so the console is always truthful.

## Consequences

- The demo can be run many times in a row from the UI alone.
- **`make up` clears every scenario explicitly** (`scripts/scenario.sh clear`) before the smoke
  test, so each build starts from the baseline. We do not rely on Helm for this: its
  three-way merge restores a patched ConfigMap's *data* but leaves the scenario
  *annotations*, which would leave the console showing a fault that is no longer there.
  The smoke test still judges the edge gateway against the live scenario state
  (`maestro.io/change-id` present → expect 503) so `make smoke` is truthful at any time.
- The APIM scenario doubles as the change-management story: the agent finds the
  change id and recommends rollback, as in the reference sketch.

## Alternatives considered

- Chaos Mesh / LitmusChaos — heavyweight for three deterministic faults.
- Synthetic metrics — would teach the agents to read fake signals; real faults keep
  the skills honest.
