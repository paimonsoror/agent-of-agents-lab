"""The Assessment contract (docs/contracts.md) as a JSON schema and prompt text.

The model produces the judgement fields; the orchestrator stamps trace_id, question,
findings, not_consulted, model and duration so they are always exact.
"""

from __future__ import annotations

_DOMAIN_VERDICT = {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "description": "Domain id: apim, cache, messaging, ..."},
        "confidence": {"type": "number", "description": "The domain agent's confidence, between 0 and 1 inclusive."},
        "headline": {"type": "string", "description": "One line from the domain finding."},
    },
    "required": ["domain", "confidence", "headline"],
    "additionalProperties": False,
}

ASSESSMENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "description": "One or two sentences: which domains are implicated and which are cleared."},
        "implicated": {"type": "array", "items": _DOMAIN_VERDICT, "description": "Domains contributing to the problem, most likely first."},
        "cleared": {"type": "array", "items": _DOMAIN_VERDICT, "description": "Domains consulted and found healthy."},
        "next_step_for_human": {"type": "string", "description": "The single most useful next action for the responder, concrete and specific."},
    },
    "required": ["verdict", "implicated", "cleared", "next_step_for_human"],
    "additionalProperties": False,
}

PREAMBLE = """You are Maestro, the central orchestrator of an enterprise observability fleet — an agent of agents.
A consumer (an incident bridge or an engineer in their IDE) has asked you a question about a problem.
Domain agents are available to you as tools named <domain>_assess. Each one investigates its own
technology domain and returns a structured Finding with evidence.

How to work:
- Decide which domains could plausibly be involved from the question. When in doubt, ask more domains rather than fewer — ask them in parallel in a single turn.
- Only the domains whose tools are present are visible to this caller; never invent others.
- Weigh findings by their evidence and confidence; a domain can be implicated, cleared, or inconclusive.
- You recommend; humans act. Your next_step_for_human must be one concrete action, naming the change id, route, group or key space involved.
- Write for a responder under pressure: short, specific, numbers included.
- Your final answer is a JSON object matching the Assessment schema you were given, and nothing else.
"""


def user_prompt(question: str, trace_id: str, caller: dict, visible: list[str], not_visible: list[str], now_iso: str) -> str:
    who = caller.get("username") or caller.get("azp") or caller.get("sub") or "unknown"
    nv = ", ".join(not_visible) if not_visible else "none"
    return (
        f"Trace: {trace_id}\nTime (UTC): {now_iso}\nCaller: {who} (client {caller.get('azp', '?')}, roles {', '.join(caller.get('roles', []))})\n"
        f"Domains visible to this caller: {', '.join(visible) or 'none'}\n"
        f"Domains NOT visible to this caller (do not attempt): {nv}\n\n"
        f"Question:\n{question}\n\n"
        "Consult the relevant domain agents, then return the Assessment JSON."
    )
