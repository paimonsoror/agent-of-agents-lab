# Kafka metrics via kafka-exporter — exact queries

Job `kafka-exporter`, port 9308. Offsets and lag are **gauges**: never `rate()` lag;
`rate()` of `current_offset` is the produce rate.

## Consumer group

```promql
sum(kafka_consumergroup_lag{job="kafka-exporter",consumergroup="portal-consumer"})
sum by (topic, partition) (kafka_consumergroup_lag{job="kafka-exporter",consumergroup="portal-consumer"})
max(kafka_consumergroup_members{job="kafka-exporter",consumergroup="portal-consumer"})
sum(kafka_consumergroup_current_offset{job="kafka-exporter",consumergroup="portal-consumer"})
```

Use `query_prometheus_range(<lag expr>, 30)`: `first` vs `last` gives growth; `min` near
`first` and `max == last` indicates monotonic growth.

## Producers / topic

```promql
sum(rate(kafka_topic_partition_current_offset{job="kafka-exporter",topic="member.events"}[5m]))
sum by (topic) (kafka_topic_partitions{job="kafka-exporter"})
sum(kafka_topic_partition_under_replicated_partition{job="kafka-exporter"})
sum(kafka_topic_partition_leader_is_preferred{job="kafka-exporter",topic="member.events"})
```

## Cluster

```promql
max(kafka_brokers{job="kafka-exporter"})
up{job="kafka-exporter"}
```

## Application view (member portal)

```promql
sum(rate(portal_events_published_total{job="portal-api"}[5m]))
sum(rate(portal_consumer_events_consumed_total{job="portal-consumer"}[5m]))
up{job="portal-consumer"}
```

If `up{job="portal-consumer"}` returns no series, the Service has no endpoints: the
Deployment is at zero replicas or its pods are not ready.

## Drain-time estimate

`drain_minutes = total_lag / (normal_consume_rate_per_s * 60)`. Use the consumer's last
healthy rate from a 60-minute range if the recent 5m rate is 0.
