"""Tools every domain agent has regardless of domain: skill references and the shared Prometheus."""

from __future__ import annotations

from typing import Any

from maestro_common.events import emit
from maestro_common.llm import ToolSpec
from maestro_common.prom import PrometheusClient
from maestro_common.skills import Skill, read_reference


def build_common_tools(skills: list[Skill]) -> list[ToolSpec]:
    by_name = {s.name: s for s in skills}
    prom = PrometheusClient()

    async def _read_reference(args: dict[str, Any]) -> str:
        skill = by_name.get(args["skill"])
        if skill is None:
            raise ValueError(f"unknown skill {args['skill']!r}; loaded: {sorted(by_name)}")
        text = read_reference(skill, args["file"])
        emit("skills.loaded", f"Consulted {skill.name}/references/{args['file']}", to="skills",
             detail={"skill": skill.name, "file": args["file"]})
        return text

    async def _query(args: dict[str, Any]) -> str:
        return await prom.query(args["expr"])

    async def _query_range(args: dict[str, Any]) -> str:
        return await prom.query_range(args["expr"], minutes=int(args["minutes"]))

    async def _targets(_: dict[str, Any]) -> Any:
        targets = await prom.targets()
        emit("evidence.gathered", f"Listed {len(targets)} active Prometheus targets", to="prometheus")
        return targets

    return [
        ToolSpec(
            name="read_reference",
            description="Read one reference file bundled with a loaded skill (progressive disclosure). Use it when the skill text points you to a reference for thresholds, dashboards or runbooks.",
            input_schema={
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "Skill name, e.g. cache-observability"},
                    "file": {"type": "string", "description": "File name under the skill's references/ folder"},
                },
            },
            handler=_read_reference,
        ),
        ToolSpec(
            name="query_prometheus",
            description="Run an instant PromQL query against the shared monitoring Prometheus. Returns one line per series.",
            input_schema={
                "type": "object",
                "properties": {"expr": {"type": "string", "description": "PromQL expression"}},
            },
            handler=_query,
        ),
        ToolSpec(
            name="query_prometheus_range",
            description="Run a PromQL range query over the last N minutes. Returns first/min/max/last per series — use it to see a trend.",
            input_schema={
                "type": "object",
                "properties": {
                    "expr": {"type": "string", "description": "PromQL expression"},
                    "minutes": {"type": "integer", "description": "Look-back window in minutes, e.g. 30"},
                },
            },
            handler=_query_range,
        ),
        ToolSpec(
            name="list_prometheus_targets",
            description="List active Prometheus scrape targets (job, instance, health). Use it to confirm an exporter is up before trusting an absence of data.",
            input_schema={"type": "object", "properties": {}},
            handler=_targets,
        ),
    ]
