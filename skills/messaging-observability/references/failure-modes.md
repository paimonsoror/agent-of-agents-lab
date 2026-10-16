# Messaging failure modes (Kafka)

## 1. Consumer gone (scaled to zero, crash loop, wrong group id)

- **Looks like:** group state `Empty`, members 0, lag growing linearly at the produce rate,
  produce rate normal, `up{job="portal-consumer"}` absent or 0.
- **Confirm:** `kafka_consumer_group_lag("portal-consumer")`; members range query shows the
  drop moment.
- **Recommend:** restore the consumer deployment; estimate drain time = lag / normal consume
  rate. Confidence 0.8–0.9 (consumer-side).

## 2. Consumer slow (present but behind)

- **Looks like:** members ≥ 1, lag growing but slower than the produce rate, consume rate
  < produce rate, consumer p95 processing time up.
- **Confirm:** compare `rate(portal_consumer_events_consumed_total)` with produce rate; group `Stable`.
- **Recommend:** scale consumers up to the partition count; investigate the consumer's
  downstream dependency. Confidence 0.7–0.85.

## 3. Rebalance storm

- **Looks like:** group flips between `PreparingRebalance`/`CompletingRebalance`/`Stable`;
  members count oscillates; lag saw-tooths.
- **Confirm:** repeated `kafka_consumer_group_lag` calls 30 s apart show different states.
- **Recommend:** check `max.poll.interval.ms` / session timeouts and consumer restarts.
  Confidence 0.7.

## 4. Broker down / unreachable

- **Looks like:** `kafka_brokers == 0` or the exporter target down; produce rate falls to
  0; `kafka_broker_status()` fails; portal reports publish errors.
- **Confirm:** `kafka_broker_status()`, `up{job="kafka-exporter"}`,
  `rate(portal_events_published_total)`.
- **Recommend:** restart/inspect the Kafka pod in `domain-messaging`. Confidence 0.9–0.95.

## 5. Topic missing or misconfigured

- **Looks like:** producers error, `kafka_describe_topics()` lacks `member.events`, or
  partitions = 0.
- **Confirm:** describe topics.
- **Recommend:** recreate the topic per the platform's catalogue. Confidence 0.9.

## 6. Under-replicated partitions

- **Looks like:** `kafka_topic_partition_under_replicated_partition > 0`.
- **Reality here:** replication factor 1 on a single broker — this metric is always 0.
  Mention it as "not applicable in this topology" if the question raises replication.

## 7. Disk full / retention

- **Looks like:** produce errors with the broker up; oldest offsets advancing fast.
- **Confirm:** broker status; `kafka_topic_partition_oldest_offset` rate.
- **Recommend:** retention/disk review. Confidence 0.6 without broker logs.

## Thresholds (steady state from the load generator, ~3 msg/s)

| Signal | Normal | Degraded | Severe |
| --- | --- | --- | --- |
| total lag (portal-consumer) | < 50 | 50–500 | > 500 or growing for 10m |
| members | ≥ 1 | oscillating | 0 |
| produce rate | 2–5 msg/s | < 1 msg/s | 0 |
| consume/produce ratio | 0.8–1.2 | 0.5–0.8 | < 0.5 |
| brokers | 1 | — | 0 |
