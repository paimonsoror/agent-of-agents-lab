"""Prometheus metrics every first-party service exposes on /metrics. Scraped by the shared stack."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, make_asgi_app

from maestro_common.config import settings

_svc = settings.service_name

LLM_TOKENS = Counter("maestro_llm_tokens_total", "LLM tokens by kind", ["service", "model", "kind"])
LLM_TURNS = Counter("maestro_llm_turns_total", "LLM turns (requests to the model)", ["service", "model"])
TOOL_CALLS = Counter("maestro_tool_calls_total", "Tool calls made by the LLM loop", ["service", "tool", "outcome"])
REQUESTS = Counter("maestro_requests_total", "Inbound agent requests", ["service", "operation", "outcome"])
REQUEST_SECONDS = Histogram(
    "maestro_request_seconds", "Inbound request duration", ["service", "operation"],
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300),
)


def record_usage(model: str, usage) -> None:  # usage: anthropic Usage object
    for kind in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = getattr(usage, kind, None) or 0
        if value:
            LLM_TOKENS.labels(_svc, model, kind).inc(value)
    LLM_TURNS.labels(_svc, model).inc()


metrics_app = make_asgi_app()
