"""The agentic loop shared by Maestro and the domain agents (ADR-0010).

A manual loop rather than the SDK's beta tool runner, because each tool call must emit a
Fleet Console event, parallel tool_use blocks must run concurrently, and the final answer
must be validated against a JSON schema. Thinking blocks are returned verbatim to the model.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import anthropic

from maestro_common.config import settings
from maestro_common.events import emit
from maestro_common.metrics import TOOL_CALLS, record_usage

log = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    strict: bool = True

    def as_param(self) -> dict[str, Any]:
        schema = dict(self.input_schema)
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        if self.strict:
            schema.setdefault("additionalProperties", False)
            schema.setdefault("required", list(schema["properties"].keys()))
        spec = {"name": self.name, "description": self.description, "input_schema": schema}
        if self.strict:
            spec["strict"] = True
        return spec


@dataclass
class LoopResult:
    text: str
    structured: dict[str, Any] | None
    turns: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""


class LLMLoop:
    def __init__(
        self,
        *,
        system: str,
        tools: list[ToolSpec],
        model: str | None = None,
        effort: str | None = None,
        max_turns: int | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> None:
        self.system = system
        self.tools = {t.name: t for t in tools}
        self.model = model or settings.llm_model
        self.effort = effort or settings.llm_effort
        self.max_turns = max_turns or settings.llm_max_turns
        self.output_schema = output_schema
        self._client = anthropic.AsyncAnthropic()

    async def _create(self, messages: list[dict[str, Any]]) -> Any:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 16000,
            "system": [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "tools": [t.as_param() for t in self.tools.values()],
            "output_config": {"effort": self.effort},
        }
        if self.output_schema:
            params["output_config"]["format"] = {"type": "json_schema", "schema": self.output_schema}
        if settings.llm_fallbacks:
            return await self._client.beta.messages.create(
                betas=[_FALLBACK_BETA], fallbacks=settings.llm_fallbacks, **params
            )
        return await self._client.messages.create(**params)

    async def run(self, user_content: str) -> LoopResult:
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
        result = LoopResult(text="", structured=None, turns=0, model=self.model)

        for _ in range(self.max_turns):
            response = await self._create(messages)
            result.turns += 1
            record_usage(self.model, response.usage)
            emit(
                "llm.turn",
                f"{self.model} turn {result.turns}: stop={response.stop_reason}",
                detail={"usage": response.usage.to_dict(), "effort": self.effort},
            )

            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                raise RuntimeError(f"model refused: {getattr(details, 'explanation', '')}")

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                result.text = "".join(b.text for b in response.content if b.type == "text")
                result.structured = self._parse_structured(result.text)
                return result

            messages.append({"role": "assistant", "content": response.content})
            outcomes = await asyncio.gather(*(self._call(b.name, b.input) for b in tool_uses))
            tool_results = []
            for block, (content, is_error) in zip(tool_uses, outcomes):
                result.tool_calls.append({"tool": block.name, "input": block.input, "is_error": is_error})
                item: dict[str, Any] = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                if is_error:
                    item["is_error"] = True
                tool_results.append(item)
            messages.append({"role": "user", "content": tool_results})

        raise RuntimeError(f"LLM loop exceeded {self.max_turns} turns without a final answer")

    async def _call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        spec = self.tools.get(name)
        if spec is None:
            TOOL_CALLS.labels(settings.service_name, name, "unknown").inc()
            return f"Unknown tool {name}", True
        try:
            value = await spec.handler(args)
            TOOL_CALLS.labels(settings.service_name, name, "ok").inc()
            return value if isinstance(value, str) else json.dumps(value, default=str), False
        except Exception as exc:  # noqa: BLE001 - errors go back to the model
            log.warning("tool %s failed: %s", name, exc)
            TOOL_CALLS.labels(settings.service_name, name, "error").inc()
            emit("error", f"tool {name} failed: {exc}"[:300])
            return f"Error from {name}: {exc}", True

    def _parse_structured(self, text: str) -> dict[str, Any] | None:
        if not self.output_schema:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            log.error("structured output did not parse: %s", text[:300])
            return None
