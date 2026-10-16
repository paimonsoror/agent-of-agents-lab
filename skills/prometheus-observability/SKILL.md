---
name: prometheus-observability
description: How to use the fleet's shared monitoring (Prometheus + Grafana) as evidence. Use whenever you query metrics, write PromQL, check scrape targets, compute rates or ratios, or need to cite a Grafana panel. Covers query hygiene, the fleet's job/label conventions, how to turn a number into an evidence item, and how to build dashboard deep links.
metadata:
  domain: shared
  version: "1.0"
  owner: platform-observability
---

# Shared monitoring: Prometheus and Grafana

Every domain in this enterprise already sends metrics to one Prometheus and reads them
in one Grafana. You are an expert user of that stack. Your domain skill tells you
*which* metrics matter; this skill tells you *how* to query them correctly and how to
turn what you see into evidence a responder can trust.

## Tools you have for this

| Tool | Use it for |
| --- | --- |
| `query_prometheus(expr)` | An instant query. Returns `series = value` lines. Best for "what is it right now" and ratios. |
| `query_prometheus_range(expr, minutes)` | A range query summarised as first/min/max/last per series. Best for "did it change, and when". |
| `list_prometheus_targets()` | Scrape target health. Call it when a query returns nothing — a missing exporter is itself evidence. |
| `read_reference(skill, file)` | Load `references/promql-cookbook.md` or `references/fleet-metrics-catalog.md` from this skill when you need an exact expression or metric name. |

## Query hygiene (follow every time)

1. **Counters need `rate()`.** Any metric ending in `_total` is a counter. Never compare raw
   counter values; use `rate(metric[5m])` (per second) or `increase(metric[5m])` (per window).
2. **Use a 5m window** for rates unless the skill says otherwise. 1m windows are noisy with
   15 s scrapes; 30m windows hide the moment a fault started.
3. **Aggregate deliberately.** Always `sum by (label)` to the labels you will cite. Do not
   return 50 per-partition or per-instance series when one aggregate answers the question.
4. **Ratios are `rate / rate`,** guarded against divide-by-zero with `clamp_min(denominator, 1e-9)`
   or by checking the denominator first. Report ratios as percentages with one decimal.
5. **Histograms:** p95 is `histogram_quantile(0.95, sum by (le) (rate(<metric>_bucket[5m])))`.
6. **Check the window of the incident.** For "when did this start", run
   `query_prometheus_range` over 30 minutes and compare `first` to `last`; a flat line that
   is already bad means the problem predates the window — say so.
7. **Empty result ≠ zero.** If a query returns `(no series matched)`, the metric name or label
   is wrong, or the exporter is down. Check `list_prometheus_targets()` before concluding.
8. **Never invent numbers.** Quote the value the tool returned, with its unit and window.

## Label conventions in this fleet

The `job` label equals the Kubernetes Service name that is scraped. Use it to scope every
query to the platform you own:

| job | What it is | Namespace |
| --- | --- | --- |
| `edge-gateway` | agentgateway acting as the API-management edge (member portal's public API) | `domain-apim` |
| `fleet-gateway` | agentgateway in front of the agents (MCP) | `maestro-gateway` |
| `valkey-exporter` | redis_exporter for the Valkey cache | `domain-cache` |
| `kafka-exporter` | kafka-exporter for the Kafka cluster | `domain-messaging` |
| `portal-api` | the member portal API (sample business application) | `member-portal` |
| `portal-consumer` | the member portal's Kafka consumer | `member-portal` |
| `apim-agent`, `cache-agent`, `messaging-agent`, `maestro` | the agents themselves (`maestro_*` metrics) | domain namespaces / `maestro` |

Other labels you will meet: `namespace`, `pod`, `instance` (added by Prometheus),
`route`/`status`/`method` (gateways), `consumergroup`/`topic`/`partition` (Kafka),
`db`/`cmd` (Valkey), `route`/`status`/`result` (portal).

## From signal to evidence

An evidence item is one object in the `evidence` array of your Finding. Build it like this:

```json
{
  "source": "prometheus",
  "query": "sum(rate(redis_evicted_keys_total{job=\"valkey-exporter\"}[5m]))",
  "observation": "Evictions rose from 0/s to 412/s between 20:03 and 20:06 UTC and are still 380/s",
  "link": "http://<grafana>/d/domain-cache?viewPanel=2&from=now-30m&to=now"
}
```

Rules:

- `query` is the exact expression you ran. `observation` is a sentence with numbers, units,
  the window, and the direction of change. No adjectives without a number.
- One observation per evidence item. Two signals that corroborate each other are two items.
- Prefer a range observation ("rose from X to Y over 10m") over an instant one when you are
  claiming something *changed*.
- Add a `link` whenever your domain skill names a panel for that signal.

## Grafana deep links

`GRAFANA_PUBLIC_URL` is given to you in the request. Build links as:

```
{GRAFANA_PUBLIC_URL}/d/{dashboard_uid}?viewPanel={panel_id}&from=now-30m&to=now
```

Dashboard UIDs: `domain-apim`, `domain-cache`, `domain-messaging`, `member-portal`,
`maestro-fleet`. Panel ids are listed in each domain skill. Use `viewPanel` so the
responder lands on the one chart you looked at. For "whole dashboard" links omit `viewPanel`.

## Confidence from monitoring evidence

- A single metric crossing a threshold: at most **0.6**.
- Two independent metrics that agree (for example evictions *and* hit-ratio collapse,
  or 5xx rate *and* a recent change): **0.8–0.9**.
- Two agreeing metrics plus a platform-native confirmation from your own tools
  (`INFO`, consumer-group describe, route config): **0.9–0.95**.
- Never above **0.95**; you are reading telemetry, not the code.
- For a *cleared* verdict you need the same standard in reverse: every key metric inside
  its normal band over the last 30 minutes and the exporter target healthy.

## When Prometheus itself is the problem

If `list_prometheus_targets()` shows your exporter `down`, or every query returns empty,
report `implicated: false`, `confidence: 0.3`, headline "Monitoring blind spot for
<domain>", and recommend restoring the exporter. Do not guess the platform's state.

## Output

Your domain skill defines the Finding JSON. This skill only governs the `evidence`
items and the confidence you may claim from them.
