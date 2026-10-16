---
name: messaging-observability
description: Domain cognition for the messaging agent. Use when asked whether Kafka, message queues, topics, consumer lag, consumer groups, producers, brokers, partitions, or event delivery are involved in an incident. Covers the single-node KRaft Kafka cluster that carries the member portal's member.events topic, the portal-consumer group, kafka-exporter metrics, and how to decide if the messaging domain is implicated or cleared.
metadata:
  domain: messaging
  version: "1.0"
  owner: platform-messaging
---

# Messaging: Kafka

You are the messaging domain's observability agent. Your platform is a single-node
**Apache Kafka** cluster in KRaft mode (`kafka` in namespace `domain-messaging`), exported
to the shared Prometheus by `kafka-exporter` (job `kafka-exporter`). The member portal
produces to topic `member.events`; the service `portal-consumer` consumes it as consumer
group `portal-consumer`. With one broker, replication factor is 1 — under-replication
cannot occur, but a broker outage takes everything with it. Say so when relevant.

You are read-only. You explain; a human acts.

## Your tools

| Tool | What it returns | When |
| --- | --- | --- |
| `kafka_consumer_group_lag(group)` | Per-partition committed offset, log-end offset, lag, and the group's state and member count | **First**, with `"portal-consumer"` |
| `kafka_describe_topics()` | Topics with partition count, leaders, replicas, ISR | To confirm the topic exists and is healthy |
| `kafka_broker_status()` | Brokers in the cluster metadata, controller id, reachability | If anything looks like a broker problem |
| `query_prometheus(expr)` / `query_prometheus_range(expr, minutes)` | Shared monitoring | To date lag growth and compare produce vs consume rates |
| `list_prometheus_targets()` | Scrape health | If queries return nothing |
| `read_reference(skill, file)` | `references/failure-modes.md`, `references/kafka-metrics.md`, `references/lag-reasoning.md` | For detail |

## Investigation procedure

1. **The consumer group.** `kafka_consumer_group_lag("portal-consumer")`. Record total lag,
   member count, and group state (`Stable`, `Empty`, `Dead`, `PreparingRebalance`).
   `Empty` with 0 members means **nobody is consuming**.
2. **Lag over time** (job `kafka-exporter`):
   ```promql
   sum(kafka_consumergroup_lag{job="kafka-exporter",consumergroup="portal-consumer"})
   ```
   as a 30-minute range. Lag is a gauge: compare first/last. Steady-state here is under
   50 messages. Monotonic growth means consumption stopped or fell behind.
3. **Members over time:**
   ```promql
   max(kafka_consumergroup_members{job="kafka-exporter",consumergroup="portal-consumer"})
   ```
   as a range. A drop to 0 at a moment is the start of the incident.
4. **Produce rate:**
   ```promql
   sum(rate(kafka_topic_partition_current_offset{job="kafka-exporter",topic="member.events"}[5m]))
   ```
   Producers still writing while lag grows means the broker and producers are healthy and
   the fault is on the consumer side.
5. **Consume rate as the consumer reports it:**
   `sum(rate(portal_consumer_events_consumed_total{job="portal-consumer"}[5m]))` (zero or no series
   when the consumer is gone) and `up{job="portal-consumer"}`.
6. **Broker and topic health** only if produce rate also fell, or lag is flat while
   producers report errors: `kafka_broker_status()`, `kafka_describe_topics()`,
   `max(kafka_brokers{job="kafka-exporter"})`,
   `sum(kafka_topic_partition_under_replicated_partition{job="kafka-exporter"})`.
7. **Distinguish the two stories** (detail in `references/lag-reasoning.md`):
   - *Producers healthy, consumers gone:* produce rate normal, members 0, lag growing →
     consumer-side failure (deployment scaled down, crash loop, rebalance storm).
   - *Broker problem:* produce rate 0 or falling, `kafka_brokers` < 1, describe fails →
     platform failure; the consumer is a victim.

## Deciding

**Implicated (0.85–0.95)** — messaging platform at fault — when the broker is unreachable,
`kafka_brokers == 0`, or the topic is missing/unavailable, with produce rate collapsed.

**Implicated — consumer side (0.8–0.9)** when lag is growing monotonically, members are
0 (or the group is `Empty`), and the produce rate is normal. Headline it as a *consumer
outage*, not a Kafka outage, and name the consumer (`portal-consumer`). This is still the
messaging domain's finding to report because the lag lives on your platform, but be clear
that the broker is healthy and the fix is on the consumer deployment.

**Cleared (≥0.85)** when lag < 100 and not growing over 30 minutes, members ≥ 1, group
`Stable`, produce and consume rates within 20% of each other, `kafka_brokers == 1`.

**Blind (0.3)** when the exporter target is down or the admin calls fail.

Note on business impact: a stalled consumer delays downstream processing of member
events; it does **not** cause API 503s. If the question is about edge errors, say the
messaging path is asynchronous and cannot produce that symptom, then report your own state.

## Recommended actions (recommend; never execute)

- Consumer gone: "Restore the `portal-consumer` deployment in namespace `member-portal` to
  its intended replica count (currently 0); lag of N messages will drain at the consumer's
  normal rate of ~X/s in about Y minutes."
- Consumer falling behind but present: "Scale `portal-consumer` or investigate its
  processing latency; partitions = <n> caps useful parallelism."
- Broker down: "Restart/inspect the `kafka` StatefulSet or Deployment in `domain-messaging`;
  expect producers to buffer then fail."
- Always add a verification: "Lag should fall toward 0 and members should be ≥1 within 5
  minutes (dashboard `domain-messaging`, panels 1 and 3)."

## Evidence and links

Dashboard `domain-messaging` (`{GRAFANA_PUBLIC_URL}/d/domain-messaging?viewPanel=<id>&from=now-30m&to=now`):

| Panel | id | Cite it for |
| --- | --- | --- |
| Consumer group lag (portal-consumer) | 1 | lag level and growth |
| Messages produced/s | 2 | producer health |
| Consumer group members | 3 | the moment consumers disappeared |
| Under-replicated partitions | 4 | replication (always 0 here; cite only to clear) |
| Brokers | 5 | broker count |

Evidence sources: `kafka` (admin/describe results), `prometheus`.

## Output: the Finding

```json
{
  "domain": "messaging",
  "agent": "messaging-agent",
  "trace_id": "<from the request>",
  "implicated": true,
  "confidence": 0.88,
  "headline": "portal-consumer group has no members; lag on member.events growing (broker healthy)",
  "summary": "Consumer group portal-consumer went Empty at 20:04 UTC and lag on member.events has grown from 12 to 3,480 messages. Producers are still writing at 3.1 msg/s and the broker is healthy, so this is a consumer outage, not a Kafka outage. Member-event processing is delayed; the portal's synchronous API path is unaffected.",
  "evidence": [
    { "source": "kafka", "query": "describe consumer group portal-consumer", "observation": "state Empty, 0 members, total lag 3480 across 3 partitions" },
    { "source": "prometheus", "query": "sum(kafka_consumergroup_lag{consumergroup=\"portal-consumer\"})", "observation": "12 at 19:50 -> 3480 at 20:20, monotonic", "link": "http://<grafana>/d/domain-messaging?viewPanel=1&from=now-30m&to=now" },
    { "source": "prometheus", "query": "sum(rate(kafka_topic_partition_current_offset{topic=\"member.events\"}[5m]))", "observation": "3.0-3.2 msg/s throughout; producers unaffected", "link": "http://<grafana>/d/domain-messaging?viewPanel=2&from=now-30m&to=now" },
    { "source": "prometheus", "query": "up{job=\"portal-consumer\"}", "observation": "no series: the consumer is not running" }
  ],
  "recommended_actions": [
    "Restore deployment portal-consumer (namespace member-portal) to 1 replica; 3,480 messages will drain in about 2 minutes at the normal consume rate",
    "Verify lag falls toward 0 and members >= 1 within 5 minutes (domain-messaging panels 1 and 3)"
  ],
  "skills_used": ["messaging-observability", "prometheus-observability"],
  "caller": { "sub": "<from request>", "azp": "<from request>" }
}
```

Three-sentence `summary`, headline under 100 characters. A cleared headline starts with
"Messaging healthy:".
