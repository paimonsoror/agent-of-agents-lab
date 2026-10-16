# 0007. Agent cognition lives in agentskills.io `SKILL.md` bundles

Date: 2026-10-15
Status: Accepted

## Context

The value of a domain agent is what it knows: the platform's failure modes, the
signals that matter, how to read the shared dashboards, what "implicated" means. That
knowledge must be owned by domain teams, reviewed like code, and portable across
agent runtimes. The [Agent Skills specification](https://agentskills.io/specification)
defines a `SKILL.md` with YAML frontmatter (`name`, `description`, optional
`metadata`) and optional `references/`, `scripts/`, `assets/` directories, loaded by
progressive disclosure.

## Decision

- `skills/` holds one directory per skill, spec-compliant (name == directory, ≤64
  chars, lowercase-hyphen; description ≤1024 chars; `SKILL.md` ≤500 lines).
- Each domain agent loads the skills named in `AGENT_SKILLS`: the full `SKILL.md`
  body goes into the (prompt-cached) system prompt; `references/` files are listed
  by name and fetched on demand with a `read_reference(skill, file)` tool.
- Maestro has its own skill, `maestro-orchestration` (triage, which domains to ask,
  scoring, writing for responders).
- Skills are copied into the images at build time; no runtime fetch.
- Code in `agents/` is domain-agnostic plumbing. Domain-specific *tools* (Valkey
  `INFO`, Kafka lag) live in `agents/domain-agent/domains/<domain>.py` and are
  described to the model by the skill, which tells it when to use which.

## Consequences

- A domain team can improve their agent with a pull request to one Markdown file.
- The Fleet Console shows "skills loaded" per request, making cognition visible.
- `metadata.version` on each skill is surfaced in findings (`skills_used`).
- We validate frontmatter at image build (`scripts/validate-skills.py`).

## Alternatives considered

- Prompts embedded in Python — not reviewable by domain owners, not portable.
- RAG over runbooks — more machinery, less determinism; skills can link to runbooks.
- MCP prompts/resources as the cognition carrier — ties knowledge to transport.
