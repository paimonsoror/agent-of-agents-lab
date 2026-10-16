# Assessment examples

## A. One domain implicated, two cleared (the standard demo)

Question: "P1: member portal API returning 503s for /api/members."

Findings: apim implicated 0.87 (change CHG0123, 5xx 98%, probe 503, portal healthy);
cache cleared 0.9; messaging cleared 0.88.

```json
{
  "trace_id": "trc-20261015-200312-7f3a",
  "question": "P1: member portal API returning 503s for /api/members.",
  "verdict": "API management is implicated with 0.87 confidence: change CHG0123 repointed /api/members to a non-existent backend at 20:02 UTC and the edge has returned 503 since 20:04. Cache and messaging are healthy.",
  "implicated": [{ "domain": "apim", "confidence": 0.87, "headline": "Edge route /api/members was repointed to a non-existent backend by CHG0123" }],
  "cleared": [
    { "domain": "cache", "confidence": 0.9, "headline": "Cache healthy: 0 evictions/s, hit ratio 0.95, memory 41% of max" },
    { "domain": "messaging", "confidence": 0.88, "headline": "Messaging healthy: lag 14, 1 member, producers 3.1 msg/s" }
  ],
  "not_consulted": [],
  "next_step_for_human": "Roll back change CHG0123 on the edge gateway (ConfigMap edge-gateway-config, namespace domain-apim) and confirm /api/members returns 200 and the 5xx ratio is below 1% within 2 minutes.",
  "findings": ["<three Finding objects>"]
}
```

## B. Caller cannot see one domain (engineer in the IDE)

Caller `engineer` has `domain:apim` and `domain:cache` only. Tools visible: `apim_assess`,
`cache_assess`.

```json
{
  "verdict": "Cache is implicated with 0.91 confidence: Valkey is at 99.9% of maxmemory and evicting ~400 keys/s since 20:05 UTC, collapsing the portal's hit ratio. The edge gateway is healthy; messaging could not be consulted because the caller lacks domain:messaging.",
  "implicated": [{ "domain": "cache", "confidence": 0.91, "headline": "Valkey is evicting under memory pressure from a foreign 'key:' workload" }],
  "cleared": [{ "domain": "apim", "confidence": 0.86, "headline": "Edge gateway healthy: 5xx 0.2%, p95 180 ms, no pending change" }],
  "not_consulted": [{ "domain": "messaging", "reason": "caller lacks role domain:messaging" }],
  "next_step_for_human": "Stop the workload writing 'key:' entries into Valkey (namespace domain-cache) and flush that keyspace; confirm evictions return to 0/s and hit ratio above 0.9 on dashboard domain-cache within 5 minutes."
}
```

## C. All clear

```json
{
  "verdict": "All consulted domains (apim, cache, messaging) are healthy with confidence at or above 0.85; the reported slowness is not explained by these platforms.",
  "implicated": [],
  "cleared": ["<three entries>"],
  "not_consulted": [],
  "next_step_for_human": "Engage the member-portal application team to review portal-api's own latency (p95 1.4 s with upstream platforms clean), starting with dashboard member-portal panel 2."
}
```

## D. Agent error

```json
{
  "verdict": "API management is implicated with 0.82 confidence: 5xx ratio 97% on /api/members since 20:04 UTC with change CHG0123 pending. Cache is healthy; the messaging agent returned an error and could not be assessed.",
  "not_consulted": [{ "domain": "messaging", "reason": "agent error: timeout after 120s (health check: agent reachable)" }],
  "next_step_for_human": "Roll back change CHG0123 on the edge gateway and re-run the assessment to cover messaging once its agent responds."
}
```
