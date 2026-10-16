"""The Finding contract (docs/contracts.md, ADR-0008) as a JSON schema and a prompt preamble.

The model fills the analytic fields; the server stamps identity fields (domain, agent,
trace_id, caller, skills_used) so they can never be wrong.
"""

from __future__ import annotations

EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "Where the evidence came from: prometheus, grafana, or the platform node (edge-gateway, valkey, kafka).",
        },
        "query": {"type": "string", "description": "The PromQL, command or tool call that produced the observation."},
        "observation": {"type": "string", "description": "What was seen, with numbers and time window."},
        "link": {"type": "string", "description": "Grafana deep link for a responder, or an empty string."},
    },
    "required": ["source", "query", "observation", "link"],
    "additionalProperties": False,
}

FINDING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "implicated": {"type": "boolean", "description": "True if this domain is contributing to the reported problem."},
        "confidence": {"type": "number", "description": "Confidence in the implicated verdict, between 0 and 1 inclusive."},
        "headline": {"type": "string", "description": "One line a responder reads first."},
        "summary": {"type": "string", "description": "Two or three sentences for a responder: what is happening and why you concluded it."},
        "evidence": {"type": "array", "items": EVIDENCE_SCHEMA},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["implicated", "confidence", "headline", "summary", "evidence", "recommended_actions"],
    "additionalProperties": False,
}

PREAMBLE = """You are {agent}, the observability agent for the {domain} domain of an enterprise platform fleet.
A central orchestrator (Maestro) has asked you to assess whether YOUR domain is implicated in a reported problem.

Rules:
- Investigate using your tools. Prefer the shared monitoring (Prometheus) for trends and your platform-native tools for the current state. Gather concrete numbers; never guess.
- You are read-only. Recommend actions; never claim to have taken any.
- Be decisive. If the domain is healthy, say so with evidence and high confidence ("cleared" is a first-class outcome).
- Keep the investigation bounded: a handful of well-chosen queries beats an exhaustive sweep.
- Every evidence item must name its source and the exact query/command. Add a Grafana deep link when the skill gives you one.
- Your final answer is a JSON object matching the Finding schema you were given, and nothing else.
"""


def user_prompt(question: str, trace_id: str, caller: dict, now_iso: str, grafana_url: str = "") -> str:
    who = caller.get("username") or caller.get("azp") or caller.get("sub") or "unknown"
    grafana = grafana_url.rstrip("/") or "(not configured)"
    return (
        f"Trace: {trace_id}\nTime (UTC): {now_iso}\nAsked on behalf of: {who} (client {caller.get('azp', '?')})\n"
        f"Grafana base URL for deep links (GRAFANA_PUBLIC_URL): {grafana}\n\n"
        f"Question from Maestro:\n{question}\n\n"
        "Assess your domain and return the Finding JSON."
    )
