"""Messaging domain tools: Kafka via the admin and consumer APIs (read-only)."""

from __future__ import annotations

import asyncio
from typing import Any

from confluent_kafka import Consumer, ConsumerGroupTopicPartitions, TopicPartition
from confluent_kafka.admin import AdminClient

from maestro_common import settings
from maestro_common.events import emit
from maestro_common.llm import ToolSpec

NODE = "kafka"
_TIMEOUT = 10.0


def _admin() -> AdminClient:
    return AdminClient({"bootstrap.servers": settings.kafka_bootstrap, "socket.timeout.ms": 10000})


def _consumer() -> Consumer:
    return Consumer({"bootstrap.servers": settings.kafka_bootstrap, "group.id": f"{settings.service_name}-probe",
                     "enable.auto.commit": False, "socket.timeout.ms": 10000})


def _describe_topics() -> list[dict[str, Any]]:
    md = _admin().list_topics(timeout=_TIMEOUT)
    out = []
    for name, topic in sorted(md.topics.items()):
        if name.startswith("__"):
            continue
        parts = topic.partitions.values()
        under = [p.id for p in parts if len(p.isrs) < len(p.replicas)]
        out.append({"topic": name, "partitions": len(topic.partitions), "under_replicated_partitions": under,
                    "leaders": sorted({p.leader for p in parts}), "error": str(topic.error) if topic.error else None})
    return out


def _group_lag(group: str) -> dict[str, Any]:
    admin = _admin()
    desc_future = admin.describe_consumer_groups([group])[group]
    try:
        desc = desc_future.result(timeout=_TIMEOUT)
        state, members = str(desc.state).split(".")[-1], len(desc.members)
    except Exception as exc:  # noqa: BLE001 - group may not exist yet
        state, members = f"unknown ({exc})", 0

    offsets_future = admin.list_consumer_group_offsets([ConsumerGroupTopicPartitions(group)])[group]
    committed = offsets_future.result(timeout=_TIMEOUT).topic_partitions or []
    consumer = _consumer()
    try:
        partitions = []
        total = 0
        for tp in committed:
            _, high = consumer.get_watermark_offsets(TopicPartition(tp.topic, tp.partition), timeout=_TIMEOUT)
            current = tp.offset if tp.offset >= 0 else 0
            lag = max(high - current, 0)
            total += lag
            partitions.append({"topic": tp.topic, "partition": tp.partition, "committed": current, "end": high, "lag": lag})
    finally:
        consumer.close()
    return {"group": group, "state": state, "members": members, "total_lag": total, "partitions": partitions}


def _broker_status() -> dict[str, Any]:
    md = _admin().list_topics(timeout=_TIMEOUT)
    return {"cluster_id": md.cluster_id, "controller_id": md.controller_id,
            "brokers": [{"id": b.id, "host": b.host, "port": b.port} for b in md.brokers.values()],
            "topic_count": len([t for t in md.topics if not t.startswith("__")])}


async def _describe(_: dict[str, Any]) -> list[dict[str, Any]]:
    topics = await asyncio.to_thread(_describe_topics)
    under = [t["topic"] for t in topics if t["under_replicated_partitions"]]
    emit("evidence.gathered", f"Described {len(topics)} topics; under-replicated: {under or 'none'}", to=NODE, detail={"topics": topics})
    return topics


async def _lag(args: dict[str, Any]) -> dict[str, Any]:
    result = await asyncio.to_thread(_group_lag, args["group"])
    emit("evidence.gathered", f"Consumer group {args['group']}: state={result['state']} members={result['members']} total_lag={result['total_lag']}",
         to=NODE, detail=result)
    return result


async def _brokers(_: dict[str, Any]) -> dict[str, Any]:
    result = await asyncio.to_thread(_broker_status)
    emit("evidence.gathered", f"Kafka brokers: {len(result['brokers'])} (controller {result['controller_id']})", to=NODE, detail=result)
    return result


def build_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="kafka_describe_topics",
            description="List topics with partition counts, leaders and under-replicated partitions.",
            input_schema={"type": "object", "properties": {}},
            handler=_describe,
        ),
        ToolSpec(
            name="kafka_consumer_group_lag",
            description="Describe a consumer group (state, members) and compute lag per partition from committed vs end offsets. The member portal's group is portal-consumer.",
            input_schema={"type": "object", "properties": {"group": {"type": "string", "description": "Consumer group id, usually portal-consumer"}}},
            handler=_lag,
        ),
        ToolSpec(
            name="kafka_broker_status",
            description="Cluster metadata: brokers, controller, topic count.",
            input_schema={"type": "object", "properties": {}},
            handler=_brokers,
        ),
    ]


async def health() -> dict[str, Any]:
    status = await asyncio.to_thread(_broker_status)
    return {"status": "ok" if status["brokers"] else "degraded", **status}
