# Edge gateway metrics — exact queries

All scoped to `job="edge-gateway"`. agentgateway exposes `/metrics` on port 15020; the
shared Prometheus scrapes it every 15 s.

## Traffic and errors

```promql
# requests/s by status
sum by (status) (rate(agentgateway_requests_total{job="edge-gateway"}[5m]))

# requests/s by route and status (which route is broken?)
sum by (route, status) (rate(agentgateway_requests_total{job="edge-gateway"}[5m]))

# 5xx ratio (0..1)
sum(rate(agentgateway_requests_total{job="edge-gateway",status=~"5.."}[5m]))
  / clamp_min(sum(rate(agentgateway_requests_total{job="edge-gateway"}[5m])), 1e-9)

# when did it start? run as a range query over 30 minutes and read first/last
```

## Latency

```promql
histogram_quantile(0.95, sum by (le) (rate(agentgateway_request_duration_seconds_bucket{job="edge-gateway"}[5m])))
histogram_quantile(0.95, sum by (le) (rate(agentgateway_upstream_call_duration_seconds_bucket{job="edge-gateway"}[5m])))
sum(rate(agentgateway_retries_total{job="edge-gateway"}[5m]))
```

## Health

```promql
up{job="edge-gateway"}
max(agentgateway_config_synchronized{job="edge-gateway"})
sum(rate(agentgateway_downstream_connections_total{job="edge-gateway"}[5m]))
```

## Upstream comparison (member portal)

```promql
sum by (status) (rate(portal_http_requests_total{job="portal-api"}[5m]))
histogram_quantile(0.95, sum by (le) (rate(portal_request_seconds_bucket{job="portal-api"}[5m])))
up{job="portal-api"}
```

## Reading the label set

The route label values come from the route `name` in the gateway config (for example
`members`, `health`). If a query by `route` returns nothing, run the metric bare
(`agentgateway_requests_total{job="edge-gateway"}`) once to see which labels this build
emits, then re-scope. Never assume a label that the bare query did not show.
