"""loadgen: steady synthetic traffic through the edge gateway so every metric has a baseline.

Runs forever and never exits on errors — 503s are *expected* while the apim-bad-route
scenario is active, and that is exactly what the dashboards should show.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections import Counter

import httpx2

log = logging.getLogger("portal.loadgen")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

EDGE_URL = os.environ.get("EDGE_URL", "http://edge-gateway.domain-apim").rstrip("/")
RPS = float(os.environ.get("LOADGEN_RPS", "8"))
WORKERS = int(os.environ.get("LOADGEN_WORKERS", "4"))
HOT_IDS = [f"m{n:05d}" for n in range(1, 21)]  # ~70% of lookups hit these, so the cache warms
HOT_SHARE = float(os.environ.get("LOADGEN_HOT_SHARE", "0.7"))
SUMMARY_SECONDS = 30


class Stats:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.by_status: Counter[str] = Counter()
        self.latencies: list[float] = []
        self.errors = 0

    def record(self, status: str, latency: float) -> None:
        self.by_status[status] += 1
        self.latencies.append(latency)

    def summary(self) -> str:
        total = sum(self.by_status.values())
        p95 = sorted(self.latencies)[int(len(self.latencies) * 0.95)] * 1000 if self.latencies else 0.0
        statuses = ", ".join(f"{k}={v}" for k, v in sorted(self.by_status.items()))
        return f"{total} requests in {SUMMARY_SECONDS}s [{statuses}] errors={self.errors} p95={p95:.0f}ms"


def pick_member_id() -> str:
    if random.random() < HOT_SHARE:
        return random.choice(HOT_IDS)
    return f"m{random.randint(1, 100000):05d}"


async def worker(client: httpx2.AsyncClient, stats: Stats, interval: float) -> None:
    while True:
        started = time.perf_counter()
        try:
            resp = await client.get(f"{EDGE_URL}/api/members/{pick_member_id()}")
            stats.record(str(resp.status_code), time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001 - keep generating load no matter what
            stats.errors += 1
            stats.record("conn-error", time.perf_counter() - started)
            log.debug("request failed: %s", exc)
        elapsed = time.perf_counter() - started
        await asyncio.sleep(max(0.0, interval - elapsed) + random.uniform(0, interval * 0.2))


async def health_probe(client: httpx2.AsyncClient) -> None:
    last_state = None
    while True:
        try:
            resp = await client.get(f"{EDGE_URL}/api/health")
            state = f"{resp.status_code} {resp.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            state = f"unreachable ({exc.__class__.__name__})"
        if state != last_state:
            log.info("edge health: %s", state)
            last_state = state
        await asyncio.sleep(5)


async def reporter(stats: Stats) -> None:
    while True:
        await asyncio.sleep(SUMMARY_SECONDS)
        log.info(stats.summary())
        stats.reset()


async def main() -> None:
    stats = Stats()
    interval = WORKERS / RPS  # each worker fires every WORKERS/RPS seconds → RPS overall
    log.info("load: %.1f rps via %d workers against %s", RPS, WORKERS, EDGE_URL)
    async with httpx2.AsyncClient(timeout=httpx2.Timeout(5.0)) as client:
        await asyncio.gather(
            *(worker(client, stats, interval) for _ in range(WORKERS)),
            health_probe(client),
            reporter(stats),
        )


if __name__ == "__main__":
    asyncio.run(main())
