# 0010. Claude Opus 5.5 orchestrates, Claude Sonnet 5.5 runs domain agents

Date: 2026-10-15
Status: Accepted

## Context

The agents need reliable multi-step tool use. The lab VM has no GPU and 15 GiB RAM
shared with the whole stack, which rules out a capable local model. The VM can reach
`api.anthropic.com`. The user chose the Anthropic API over local inference.

## Decision

- **Maestro**: `claude-opus-5-5`, `output_config.effort = high`. It makes the
  judgement calls (which domains, how to weigh findings, what to tell a human).
- **Domain agents**: `claude-sonnet-5-5`, `effort = medium`. They run a bounded,
  skill-guided investigation; speed matters because Maestro fans out and waits.
- Adaptive thinking (the default on these models); no `budget_tokens`; no forced
  `tool_choice` (rejected by these models) — tools are steered from the skill text and
  `strict: true` schemas.
- Server-side refusal fallbacks enabled by default (`fallbacks: "default"`, beta
  `server-side-fallback-2026-07-01`) so a safety false-positive cannot stall a demo;
  switchable off with `LLM_FALLBACKS=`.
- Structured outputs (`output_config.format`) for the Finding and Assessment schemas.
- Prompt caching on the system prompt (skills are stable); volatile data (trace id,
  question) stays in the user turn.
- Manual tool loop (not the beta tool runner) so each tool call can emit a console
  event and so parallel `tool_use` blocks are executed concurrently.
- The key is read from a Kubernetes Secret created at deploy time from
  `~/.maestro/secrets.env`; it is never in the chart values or the repo.

## Consequences

- Cost per full incident assessment is a few cents; token usage is emitted as
  `llm.turn` events and exposed as Prometheus metrics.
- Model ids are environment variables (`LLM_MODEL`) so a lab can downgrade or
  upgrade without a rebuild.
- An Ollama path was considered and is deliberately not implemented; the LLM client
  is isolated in `maestro_common/llm.py` if a lab ever needs it.

## Alternatives considered

- Local Ollama — offline and free, but weak tool use on CPU-only 8B models would
  undermine the demo's credibility.
- Sonnet for the orchestrator too — cheaper, but consolidation quality is the
  product; Opus at high effort is the right default.
