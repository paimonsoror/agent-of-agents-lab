"""portal-consumer: consumes member.events as group `portal-consumer`.

Scaling this Deployment to zero is the `messaging-lag` fault scenario (ADR-0011); while it
runs, consumer-group lag stays near zero and that is the signal the messaging agent reads.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time

from confluent_kafka import Consumer, KafkaError, KafkaException
from prometheus_client import Counter, Gauge, start_http_server

log = logging.getLogger("portal.consumer")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka.domain-messaging:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "member.events")
GROUP = os.environ.get("KAFKA_GROUP", "portal-consumer")

CONSUMED = Counter("portal_consumer_events_consumed_total", "Member events consumed", ["type"])
LAST_EVENT = Gauge("portal_consumer_last_event_timestamp_seconds", "Unix time of the last consumed event")
BROKER_UP = Gauge("portal_consumer_broker_reachable", "1 when the last poll reached the broker")

_running = True


def _stop(*_) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    start_http_server(int(os.environ.get("PORT", "8000")))

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 2000,
            "session.timeout.ms": 10000,
            "topic.metadata.refresh.interval.ms": 5000,
            "log_level": 3,
        }
    )
    consumer.subscribe([TOPIC])
    log.info("consuming %s as group %s from %s", TOPIC, GROUP, KAFKA_BOOTSTRAP)

    count = 0
    while _running:
        try:
            msg = consumer.poll(1.0)
        except KafkaException as exc:
            BROKER_UP.set(0)
            log.warning("poll failed: %s; retrying", exc)
            time.sleep(5)
            continue
        if msg is None:
            continue
        err = msg.error()
        if err is not None:
            if err.code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                log.info("topic %s not created yet; waiting", TOPIC)
                time.sleep(5)
            elif err.code() == KafkaError._PARTITION_EOF:
                pass
            else:
                BROKER_UP.set(0)
                log.warning("consumer error: %s", err)
                time.sleep(2)
            continue
        BROKER_UP.set(1)
        try:
            event_type = json.loads(msg.value()).get("type", "unknown")
        except (ValueError, AttributeError):
            event_type = "malformed"
        CONSUMED.labels(event_type).inc()
        LAST_EVENT.set(time.time())
        count += 1
        if count % 100 == 0:
            log.info("consumed %d events (last offset %s partition %s)", count, msg.offset(), msg.partition())

    log.info("shutting down after %d events", count)
    consumer.close()


if __name__ == "__main__":
    main()
