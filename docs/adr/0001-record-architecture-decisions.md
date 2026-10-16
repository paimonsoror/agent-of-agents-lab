# 0001. Record architecture decisions

Date: 2026-10-15
Status: Accepted

## Context

This repository is a reference architecture that will be read, demoed and extended by
people and by AI agents who were not present when it was designed. The *why* behind a
choice erodes fastest.

## Decision

Every significant decision is captured as a numbered ADR under `docs/adr/` using the
template in `docs/adr/README.md`. Accepted ADRs are not edited; they are superseded.
`AGENTS.md` makes writing an ADR a mandatory step for any structural change.

## Consequences

- Reviewers can check a change against the ADR it claims to implement.
- Agents extending the system have a compact, authoritative history to load.
- Small cost per change; large saving in repeated debate.

## Alternatives considered

- A single design doc that is edited in place — loses history and rationale.
- Commit messages only — not discoverable, not structured.
