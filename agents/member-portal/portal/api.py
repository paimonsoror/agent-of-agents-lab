"""portal-api: member lookups cached in Valkey, change events published to Kafka.

Every dependency failure degrades rather than crashes: a Valkey error is a cache miss, a
Kafka error is a logged, counted publish failure. The point of this service is to make the
domain platforms' health visible through an application's metrics.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import valkey.asyncio as valkey_async
from confluent_kafka import KafkaException, Producer
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.routing import Match

log = logging.getLogger("portal.api")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

VALKEY_URL = os.environ.get("VALKEY_URL", "redis://valkey.domain-cache:6379")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka.domain-messaging:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "member.events")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "60"))
ORIGIN_LATENCY_SECONDS = float(os.environ.get("ORIGIN_LATENCY_SECONDS", "0.04"))

HTTP_REQUESTS = Counter("portal_http_requests_total", "HTTP requests by route template and status", ["route", "status"])
REQUEST_SECONDS = Histogram(
    "portal_request_seconds", "HTTP request duration by route template", ["route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
CACHE_LOOKUPS = Counter("portal_cache_lookups_total", "Member cache lookups by result", ["result"])
EVENTS_PUBLISHED = Counter("portal_events_published_total", "Member events handed to the Kafka producer")
EVENTS_PUBLISH_FAILED = Counter("portal_events_publish_failed_total", "Member events that could not be published")


class Cache:
    """Valkey-backed cache that reports misses on any error instead of raising."""

    def __init__(self, url: str) -> None:
        self._client = valkey_async.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True)

    async def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = await self._client.get(key)
        except Exception as exc:  # noqa: BLE001 - cache outage is a miss, not a failure
            log.warning("cache get failed (%s): %s", key, exc)
            CACHE_LOOKUPS.labels("error").inc()
            return None
        if raw is None:
            CACHE_LOOKUPS.labels("miss").inc()
            return None
        CACHE_LOOKUPS.labels("hit").inc()
        return json.loads(raw)

    async def set(self, key: str, value: dict[str, Any]) -> None:
        try:
            await self._client.set(key, json.dumps(value), ex=CACHE_TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001
            log.warning("cache set failed (%s): %s", key, exc)

    async def ping(self) -> bool:
        try:
            return bool(await asyncio.wait_for(self._client.ping(), timeout=1.0))
        except Exception:  # noqa: BLE001
            return False

    async def close(self) -> None:
        await self._client.aclose()


class EventPublisher:
    """Fire-and-forget Kafka producer; delivery failures are counted and logged."""

    def __init__(self, bootstrap: str) -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap,
                "client.id": "portal-api",
                "socket.timeout.ms": 5000,
                "message.timeout.ms": 10000,
                "queue.buffering.max.messages": 10000,
                "log_level": 3,
            }
        )
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        while True:
            try:
                self._producer.poll(0)
            except Exception as exc:  # noqa: BLE001
                log.warning("producer poll failed: %s", exc)
            await asyncio.sleep(1.0)

    def _delivered(self, err, msg) -> None:
        if err is not None:
            EVENTS_PUBLISH_FAILED.inc()
            log.warning("publish failed: %s", err)

    def publish(self, event: dict[str, Any]) -> None:
        try:
            self._producer.produce(TOPIC, key=event["member_id"], value=json.dumps(event), callback=self._delivered)
            self._producer.poll(0)
            EVENTS_PUBLISHED.inc()
        except (BufferError, KafkaException, ValueError) as exc:
            EVENTS_PUBLISH_FAILED.inc()
            log.warning("publish rejected: %s", exc)

    async def healthy(self) -> bool:
        try:
            await asyncio.wait_for(asyncio.to_thread(self._producer.list_topics, TOPIC, 1.0), timeout=1.5)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
        await asyncio.to_thread(self._producer.flush, 3.0)


def synthesize_member(member_id: str) -> dict[str, Any]:
    """Deterministic 'origin' record so repeated lookups are comparable across runs."""
    digest = hashlib.sha256(member_id.encode()).hexdigest()
    tiers = ("bronze", "silver", "gold", "platinum")
    return {
        "member_id": member_id,
        "name": f"Member {member_id}",
        "tier": tiers[int(digest[:2], 16) % len(tiers)],
        "region": ("us-east", "us-west", "eu-central", "ap-south")[int(digest[2:4], 16) % 4],
        "points": int(digest[4:8], 16),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.cache = Cache(VALKEY_URL)
    app.state.publisher = EventPublisher(KAFKA_BOOTSTRAP)
    app.state.publisher.start()
    log.info("portal-api up: valkey=%s kafka=%s topic=%s", VALKEY_URL, KAFKA_BOOTSTRAP, TOPIC)
    try:
        yield
    finally:
        await app.state.publisher.close()
        await app.state.cache.close()


app = FastAPI(title="member-portal api", lifespan=lifespan)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    # An explicit route, not a Mount: scrapers request exactly /metrics and must not be redirected.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _route_template(request: Request) -> str:
    for route in app.router.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return "unmatched"


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    if request.url.path.startswith("/metrics"):
        return await call_next(request)
    started = time.perf_counter()
    status = "500"
    try:
        response: Response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        route = _route_template(request)
        REQUEST_SECONDS.labels(route).observe(time.perf_counter() - started)
        HTTP_REQUESTS.labels(route, status).inc()


@app.get("/api/members/{member_id}")
async def get_member(member_id: str, request: Request) -> dict[str, Any]:
    key = f"member:{member_id}"
    cached = await request.app.state.cache.get(key)
    if cached is not None:
        return {"member": cached, "source": "cache"}
    await asyncio.sleep(ORIGIN_LATENCY_SECONDS)  # simulated system-of-record latency
    member = synthesize_member(member_id)
    await request.app.state.cache.set(key, member)
    request.app.state.publisher.publish(
        {"type": "member.viewed", "member_id": member_id, "tier": member["tier"], "ts": time.time()}
    )
    return {"member": member, "source": "origin"}


@app.get("/api/health")
async def health(request: Request) -> JSONResponse:
    cache_ok, kafka_ok = await asyncio.gather(request.app.state.cache.ping(), request.app.state.publisher.healthy())
    return JSONResponse({"status": "ok", "dependencies": {"valkey": cache_ok, "kafka": kafka_ok}})


@app.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    # Liveness/readiness for Kubernetes: the process is up. Dependency health is /api/health.
    return JSONResponse({"service": "portal-api", "status": "ok"})


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_level="warning", proxy_headers=True)


if __name__ == "__main__":
    main()
