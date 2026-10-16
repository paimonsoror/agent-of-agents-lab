# 0013. Open-source stand-ins for the domain platforms

Date: 2026-10-15
Status: Accepted

## Context

The reference sketch names commercial platforms (Kong Konnect, Redis Enterprise,
Kafka/IBM MQ, VMware vCenter). The demo needs open-source equivalents that export
metrics natively and have a real failure mode to investigate. The first build covers
three domains; compute is deferred.

## Decision

| Domain | Platform | Exporter | Agent's native tools |
| --- | --- | --- | --- |
| API management | agentgateway (second instance, "edge gateway") fronting `portal-api` | built-in `/metrics` on 15020 | read route config + change annotations from the ConfigMap via the Kubernetes API; probe routes |
| Distributed cache | Valkey 9 (`maxmemory 64mb`, `allkeys-lru`) | `oliver006/redis_exporter` | `INFO` (memory, stats, keyspace), `SLOWLOG`, `CONFIG GET maxmemory*` |
| Messaging | Apache Kafka 4 (KRaft, single node) | `danielqsj/kafka-exporter` | describe topics, consumer-group lag, broker metadata |

The sample **member portal** (`portal-api`, `portal-consumer`, `loadgen`) uses all
three: the edge gateway fronts it, it caches member lookups in Valkey, and it
publishes `member.events` to Kafka. One business application depending on three
domains is what makes "which domain is implicated?" a real question.

Versions are pinned in `deploy/versions.env` (verified 2026-10-15: Kafka 4.3.1,
Valkey 9.1.2, redis_exporter v1.94.0, kafka-exporter v1.10.0, Keycloak 26.8.1,
kube-prometheus-stack 92.9.0, agentgateway v1.6.0, kindest/node v1.37.0).

## Consequences

- Every domain has a real platform, a real exporter and a real fault.
- Bitnami images are avoided (their public catalogue moved to a paid tier in 2025);
  official images are used throughout.
- Compute domain: `kube-state-metrics`/`node-exporter` from kube-prometheus-stack
  already provide the signals; only a skill, a tool module and a scenario are
  needed. Network domain would follow the same pattern with the gateway or a CNI
  exporter.

## Alternatives considered

- RabbitMQ instead of Kafka — fine too; Kafka's consumer-lag story is more
  universally recognised.
- Redis instead of Valkey — licence change; Valkey is the OSS continuation and
  speaks the same protocol, so `redis_exporter` works unchanged.
