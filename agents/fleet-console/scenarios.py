"""Fault-injection scenarios, executed through the Kubernetes API (ADR-0011).

Each scenario is reversible and its active state is derived from the cluster, never stored.
The same three operations are implemented in scripts/scenario.sh for the Makefile path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

VALKEY_IMAGE = os.environ.get("VALKEY_IMAGE", "valkey/valkey:9.1.2")

EDGE_NS, EDGE_CM, EDGE_KEY = "domain-apim", "edge-gateway-config", "config.yaml"
GOOD_HOST, BAD_HOST = "portal-api.member-portal", "portal-api-v2.member-portal"
CHANGE_ID = "CHG0123"
CACHE_NS, FILLER_JOB, FLUSH_JOB = "domain-cache", "cache-filler", "cache-flush"
PORTAL_NS, CONSUMER_DEPLOY = "member-portal", "portal-consumer"


class ScenarioUnavailable(RuntimeError):
    """Raised when the Kubernetes API is not reachable (e.g. running outside the cluster)."""


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    domain: str
    platform_node: str
    description: str


SCENARIOS: dict[str, Scenario] = {
    "apim-bad-route": Scenario(
        "apim-bad-route", "Bad route change on the edge gateway", "apim", "edge-gateway",
        f"Change {CHANGE_ID} repoints /api/members at a backend that does not exist.",
    ),
    "cache-pressure": Scenario(
        "cache-pressure", "Memory pressure on Valkey", "cache", "valkey",
        "A filler job writes far past maxmemory; Valkey evicts continuously.",
    ),
    "messaging-lag": Scenario(
        "messaging-lag", "Consumer lag on Kafka", "messaging", "kafka",
        "The portal consumer is scaled to zero; consumer-group lag grows without bound.",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class K8s:
    """Lazy in-cluster client; every method raises ScenarioUnavailable if the API is unreachable."""

    def __init__(self) -> None:
        self._core = None
        self._batch = None
        self._apps = None

    def _load(self) -> None:
        if self._core is not None:
            return
        try:
            from kubernetes import client, config

            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._core = client.CoreV1Api()
            self._batch = client.BatchV1Api()
            self._apps = client.AppsV1Api()
        except Exception as exc:  # noqa: BLE001
            raise ScenarioUnavailable(f"Kubernetes API not available: {exc.__class__.__name__}: {exc}") from exc

    def _guard(self, fn: Callable[[], Any]) -> Any:
        self._load()
        try:
            return fn()
        except ScenarioUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            from kubernetes.client.exceptions import ApiException

            if isinstance(exc, ApiException):
                raise RuntimeError(f"Kubernetes API error {exc.status}: {exc.reason}") from exc
            raise ScenarioUnavailable(f"Kubernetes API not reachable: {exc}") from exc

    # --- apim-bad-route -------------------------------------------------------------
    def apim_active(self) -> bool:
        cm = self._guard(lambda: self._core.read_namespaced_config_map(EDGE_CM, EDGE_NS))
        return "maestro.io/change-id" in (cm.metadata.annotations or {})

    def apim_apply(self) -> None:
        def _do() -> None:
            cm = self._core.read_namespaced_config_map(EDGE_CM, EDGE_NS)
            cfg = cm.data.get(EDGE_KEY, "")
            body = {
                "metadata": {
                    "annotations": {
                        "maestro.io/change-id": CHANGE_ID,
                        "maestro.io/change-summary": "Route /api/members repointed to portal-api-v2 (canary)",
                        "maestro.io/changed-at": _now(),
                        "maestro.io/changed-by": "platform-apim-bot",
                        "maestro.io/last-rollback": None,
                        "maestro.io/rolled-back-at": None,
                    }
                },
                "data": {EDGE_KEY: cfg.replace(GOOD_HOST, BAD_HOST)},
            }
            self._core.patch_namespaced_config_map(EDGE_CM, EDGE_NS, body)

        self._guard(_do)

    def apim_clear(self) -> None:
        def _do() -> None:
            cm = self._core.read_namespaced_config_map(EDGE_CM, EDGE_NS)
            cfg = cm.data.get(EDGE_KEY, "")
            body = {
                "metadata": {
                    "annotations": {
                        "maestro.io/change-id": None,
                        "maestro.io/change-summary": None,
                        "maestro.io/changed-at": None,
                        "maestro.io/changed-by": None,
                        "maestro.io/last-rollback": CHANGE_ID,
                        "maestro.io/rolled-back-at": _now(),
                    }
                },
                "data": {EDGE_KEY: cfg.replace(BAD_HOST, GOOD_HOST)},
            }
            self._core.patch_namespaced_config_map(EDGE_CM, EDGE_NS, body)

        self._guard(_do)

    # --- cache-pressure -------------------------------------------------------------
    def _job_exists(self, name: str) -> bool:
        from kubernetes.client.exceptions import ApiException

        try:
            self._batch.read_namespaced_job(name, CACHE_NS)
            return True
        except ApiException as exc:
            if exc.status == 404:
                return False
            raise

    def _delete_job(self, name: str) -> None:
        from kubernetes.client.exceptions import ApiException

        try:
            self._batch.delete_namespaced_job(name, CACHE_NS, propagation_policy="Foreground")
        except ApiException as exc:
            if exc.status != 404:
                raise

    def _job(self, name: str, command: list[str], *, deadline: int, ttl: int | None) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "backoffLimit": 0,
            "activeDeadlineSeconds": deadline,
            "template": {
                "metadata": {"labels": {"app.kubernetes.io/name": name, "maestro.io/scenario": "cache-pressure"}},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [{
                        "name": name,
                        "image": VALKEY_IMAGE,
                        "command": command,
                        "resources": {"requests": {"cpu": "50m", "memory": "32Mi"}, "limits": {"memory": "128Mi"}},
                    }],
                },
            },
        }
        if ttl is not None:
            spec["ttlSecondsAfterFinished"] = ttl
        return {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": name, "namespace": CACHE_NS}, "spec": spec}

    def cache_active(self) -> bool:
        return bool(self._guard(lambda: self._job_exists(FILLER_JOB)))

    def cache_apply(self) -> None:
        def _do() -> None:
            if self._job_exists(FILLER_JOB):
                return
            cmd = ["sh", "-c",
                   "while true; do valkey-benchmark -h valkey -p 6379 -t set -n 200000 -d 4096 -r 1000000 -q; sleep 5; done"]
            self._batch.create_namespaced_job(CACHE_NS, self._job(FILLER_JOB, cmd, deadline=3600, ttl=None))

        self._guard(_do)

    def cache_clear(self) -> None:
        def _do() -> None:
            self._delete_job(FILLER_JOB)
            self._delete_job(FLUSH_JOB)
            cmd = ["sh", "-c", "valkey-cli -h valkey -p 6379 FLUSHALL"]
            self._batch.create_namespaced_job(CACHE_NS, self._job(FLUSH_JOB, cmd, deadline=120, ttl=120))

        self._guard(_do)

    # --- messaging-lag --------------------------------------------------------------
    def messaging_active(self) -> bool:
        d = self._guard(lambda: self._apps.read_namespaced_deployment_scale(CONSUMER_DEPLOY, PORTAL_NS))
        return (d.spec.replicas or 0) == 0

    def _scale(self, replicas: int) -> None:
        self._guard(lambda: self._apps.patch_namespaced_deployment_scale(
            CONSUMER_DEPLOY, PORTAL_NS, {"spec": {"replicas": replicas}}))

    def messaging_apply(self) -> None:
        self._scale(0)

    def messaging_clear(self) -> None:
        self._scale(1)


k8s = K8s()

_ACTIVE = {"apim-bad-route": k8s.apim_active, "cache-pressure": k8s.cache_active, "messaging-lag": k8s.messaging_active}
_APPLY = {"apim-bad-route": k8s.apim_apply, "cache-pressure": k8s.cache_apply, "messaging-lag": k8s.messaging_apply}
_CLEAR = {"apim-bad-route": k8s.apim_clear, "cache-pressure": k8s.cache_clear, "messaging-lag": k8s.messaging_clear}


def list_scenarios() -> list[dict[str, Any]]:
    out = []
    for s in SCENARIOS.values():
        item: dict[str, Any] = {"name": s.name, "title": s.title, "domain": s.domain, "description": s.description}
        try:
            item["active"] = _ACTIVE[s.name]()
        except (ScenarioUnavailable, RuntimeError) as exc:
            item["active"] = None
            item["error"] = str(exc)
        out.append(item)
    return out


def apply(name: str) -> Scenario:
    s = SCENARIOS[name]
    _APPLY[name]()
    return s


def clear(name: str) -> Scenario:
    s = SCENARIOS[name]
    _CLEAR[name]()
    return s
