# Edge gateway failure modes

Each entry: what it looks like, how to confirm, what to recommend. Thresholds assume the
member portal's steady load from the load generator (a few requests per second).

## 1. Bad route change (the classic)

- **Looks like:** `status="503"` (or `404`) on one route only, starting at a sharp moment.
  Other routes fine. Upstream (`portal-api`) metrics healthy.
- **Confirm:** `get_edge_change_history()` shows an unrolled-back change whose `changed-at`
  precedes the 5xx rise by 0–3 minutes (the gateway reloads the ConfigMap within about a
  minute). `get_edge_routes()` shows the route pointing at an unknown host.
- **Recommend:** roll back the named change id. Confidence 0.85–0.95.

## 2. Upstream down or crashing

- **Looks like:** 502/503 on every route that shares the upstream; `portal-api` target
  `up == 0` or its pod restarting; portal request rate drops to zero.
- **Confirm:** `up{job="portal-api"}`, `kube_pod_container_status_restarts_total` if available,
  `probe_edge_route("/api/health")`.
- **Recommend:** hand off to the portal team; APIM **cleared** (the gateway is behaving
  correctly). Confidence for "cleared" 0.8.

## 3. Upstream returning errors

- **Looks like:** edge 5xx ratio equals the portal's own 5xx ratio.
- **Confirm:** compare `sum by (status) (rate(portal_http_requests_total[5m]))` with the
  edge's. Same shape → relay.
- **Recommend:** portal team; mention which downstream the portal depends on if its own
  metrics hint (cache misses, event publish failures). APIM cleared.

## 4. Latency at the edge

- **Looks like:** p95 > 1 s at the edge while the portal's own p95 is < 200 ms.
- **Confirm:** `agentgateway_upstream_call_duration_seconds` vs
  `agentgateway_request_duration_seconds`; a gap means time spent in the gateway
  (policies, retries). Check `agentgateway_retries_total`.
- **Recommend:** review retry/timeout policies on the route. Confidence 0.6–0.8.

## 5. Config not synchronized

- **Looks like:** `agentgateway_config_synchronized == 0`. Traffic may look *fine* because
  the previous config is still serving.
- **Confirm:** change history shows a recent change; routes returned by the API may
  differ from the ConfigMap. Say the live config is older than the file.
- **Recommend:** validate and re-apply the config; treat the pending change as unapplied.

## 6. Traffic disappeared

- **Looks like:** edge request rate falls to ~0 with no errors.
- **Confirm:** `sum(rate(agentgateway_requests_total{job="edge-gateway"}[5m]))` first vs
  last; check the load generator / clients, not the gateway.
- **Recommend:** confirm clients; APIM cleared unless the listener is down (`up` for the
  edge target).

## 7. Authentication / rate limiting

- **Looks like:** 401/403/429 statuses. Not a 5xx — do not call it an outage.
- **Confirm:** by status breakdown; check for a change that added a policy.
- **Recommend:** policy review; implicate only if a change introduced it.

## Thresholds

| Signal | Normal | Degraded | Severe |
| --- | --- | --- | --- |
| 5xx ratio (5m) | < 1% | 1–5% | > 5% |
| p95 latency | < 300 ms | 300 ms – 1 s | > 1 s |
| `config_synchronized` | 1 | — | 0 |
| Route count change | 0 | any unexplained change | — |
