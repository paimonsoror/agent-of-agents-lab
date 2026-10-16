"""Maestro's reasoning: discover visible domain agents, consult them, consolidate (ADR-0010)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import federation
from assessment import ASSESSMENT_OUTPUT_SCHEMA, PREAMBLE, user_prompt
from maestro_common import settings
from maestro_common.auth import Caller
from maestro_common.events import current_caller, current_trace, emit
from maestro_common.llm import LLMLoop, ToolSpec
from maestro_common.metrics import REQUESTS, REQUEST_SECONDS
from maestro_common.skills import Skill, load_skills, read_reference, render_system_prompt

log = logging.getLogger(__name__)

_skills: list[Skill] = []
_system: str = ""


def init() -> list[Skill]:
    global _skills, _system
    _skills = load_skills(settings.agent_skills, settings.skills_dir)
    _system = PREAMBLE + "\n\n" + render_system_prompt(_skills)
    log.info("maestro skills=%s model=%s", [s.name for s in _skills], settings.llm_model)
    return _skills


def skills() -> list[Skill]:
    return _skills


def _reference_tool() -> ToolSpec:
    by_name = {s.name: s for s in _skills}

    async def handler(args: dict[str, Any]) -> str:
        skill = by_name.get(args["skill"])
        if skill is None:
            raise ValueError(f"unknown skill {args['skill']!r}; loaded: {sorted(by_name)}")
        emit("skills.loaded", f"Consulted {skill.name}/references/{args['file']}", to="skills")
        return read_reference(skill, args["file"])

    return ToolSpec(
        name="read_reference",
        description="Read one reference file bundled with a loaded skill, e.g. triage heuristics or domain cheat-sheets.",
        input_schema={"type": "object", "properties": {"skill": {"type": "string"}, "file": {"type": "string"}}},
        handler=handler,
    )


def _assess_tool(remote: federation.RemoteTool, token: str, trace_id: str, findings: list[dict[str, Any]], errors: dict[str, str]) -> ToolSpec:
    async def handler(args: dict[str, Any]) -> Any:
        try:
            finding = await federation.call(token, remote.name, {"question": args["question"], "trace_id": trace_id})
        except Exception as exc:
            errors[remote.target] = str(exc)[:300]
            raise
        if isinstance(finding, dict):
            finding.setdefault("domain", remote.target)
            findings.append(finding)
            errors.pop(remote.target, None)  # a retry succeeded; the earlier failure is no longer "not consulted"
        return finding

    return ToolSpec(
        name=remote.name,
        description=remote.description or f"Ask the {remote.target} domain agent to assess the problem.",
        input_schema={
            "type": "object",
            "properties": {"question": {"type": "string", "description": "The problem statement, with any domain-specific angle you want investigated."}},
        },
        handler=handler,
    )


async def run_assessment(question: str, trace_id: str, caller: Caller) -> dict[str, Any]:
    current_trace.set(trace_id)
    caller_info = caller.as_dict()
    current_caller.set(caller_info)
    started = time.perf_counter()
    origin = "ide" if caller.azp == "ide-cli" else "console"
    emit("request.received", f"Maestro received: {question[:140]}", from_=origin, to="maestro",
         detail={"caller": caller_info, "question": question})
    emit("skills.loaded", "Loaded skills: " + ", ".join(f"{s.name}@{s.version}" for s in _skills), to="skills",
         detail={"skills": [{"name": s.name, "version": s.version} for s in _skills]})

    try:
        remote_tools, not_visible = await federation.discover(caller.raw_token)
    except Exception as exc:
        REQUESTS.labels(settings.service_name, "ask", "error").inc()
        emit("error", f"Maestro could not reach the fleet gateway: {exc}"[:300], to="gateway")
        raise

    findings: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    visible = sorted({t.target for t in remote_tools if t.is_assess})
    tools = [_assess_tool(t, caller.raw_token, trace_id, findings, errors) for t in remote_tools if t.is_assess]
    tools.append(_reference_tool())

    loop = LLMLoop(system=_system, tools=tools, output_schema=ASSESSMENT_OUTPUT_SCHEMA)
    try:
        result = await loop.run(user_prompt(question, trace_id, caller_info, visible, not_visible,
                                            datetime.now(timezone.utc).isoformat(timespec="seconds")))
    except Exception as exc:
        REQUESTS.labels(settings.service_name, "ask", "error").inc()
        emit("error", f"Maestro assessment failed: {exc}"[:300])
        raise

    judgement = result.structured or {
        "verdict": "Maestro could not produce a structured assessment.",
        "implicated": [],
        "cleared": [],
        "next_step_for_human": result.text[:500] or "Re-run the assessment and inspect Maestro's logs.",
    }
    answered = {f.get("domain") for f in findings}
    not_consulted = [{"domain": d, "reason": f"caller lacks role domain:{d}"} for d in not_visible]
    not_consulted += [{"domain": d, "reason": f"agent error: {msg}"} for d, msg in errors.items() if d not in answered]
    assessment = {
        "trace_id": trace_id,
        "question": question,
        **judgement,
        "not_consulted": not_consulted,
        "findings": findings,
        "caller": {"sub": caller.sub, "azp": caller.azp, "username": caller.preferred_username},
        "model": result.model,
        "turns": result.turns,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
    emit("assessment.posted", assessment["verdict"][:300], to="console", detail=assessment)
    REQUESTS.labels(settings.service_name, "ask", "ok").inc()
    REQUEST_SECONDS.labels(settings.service_name, "ask").observe(time.perf_counter() - started)
    return assessment
