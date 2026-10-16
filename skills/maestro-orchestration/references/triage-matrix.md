# Triage matrix: symptom → domains to consult

The member portal (the sample business application) depends on all three domains:

```
client → edge gateway (apim) → portal-api → Valkey (cache)
                                         ↘ Kafka member.events (messaging) → portal-consumer
```

Synchronous path: edge → portal → cache. Asynchronous path: portal → Kafka → consumer.

| Symptom (as phrased by the caller) | apim | cache | messaging | Note |
| --- | --- | --- | --- | --- |
| P1 / "portal down" / 503 / 5xx / "members endpoint failing" | **yes** | yes | yes | consult all; apim most likely root cause for hard errors |
| 404 on an API path | **yes** | no | no | route missing or renamed |
| API slow, no errors | **yes** | **yes** | no | messaging is async; cannot slow the request path |
| Timeouts at the edge | **yes** | yes | no | upstream slow vs gateway policy |
| "cache misses", "evictions", "Redis/Valkey" | yes | **yes** | no | apim to confirm user-facing latency impact |
| "Kafka", "lag", "events delayed", "consumer" | no | no | **yes** | add apim only if the caller also reports API errors |
| "notifications late" / downstream processing late | no | no | **yes** | async path |
| "after a change / deploy / rollout" | **yes** | yes | yes | every domain checks its own change history |
| "is everything healthy?" / status request | yes | yes | yes | all visible |
| Authentication / 401 / 403 on API | **yes** | no | no | policy at the edge |
| Memory alerts on a cache node | no | **yes** | no | |
| Broker alerts, under-replicated, disk | no | no | **yes** | |

**yes** = primary suspect; yes = consult for corroboration or to clear.

## Context sentence you may add to each `assess` call

Add at most one sentence that helps the agent focus, drawn from the question itself:
"Symptom: HTTP 503 from the public API for /api/members since about 20:03 UTC; please
assess your domain's involvement." Never add hypotheses about *other* domains to a domain
agent's question — it biases their investigation.

## Scoped questions

If the caller clearly scopes the question ("is the cache the problem?"), consult that
domain and the domains the symptom could propagate to (cache → apim for user impact). Put
the rest under `not_consulted` with reason `not relevant to the question` — this is the
only time that reason is acceptable.
