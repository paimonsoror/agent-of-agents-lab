# 0014. A static GitHub Pages site explains the lab

Date: 2026-10-16
Status: Accepted

## Context

The repository's Markdown documentation is written for people who will build and
extend the lab. A second audience, executives and colleagues deciding whether to
adopt the pattern, needs to understand what the lab is and what it does without
cloning anything, and benefits from seeing the request flow animated rather than
described.

## Decision

A static site lives in `site/` and is published to GitHub Pages
(`https://paimonsoror.github.io/agent-of-agents-lab/`) by
`.github/workflows/pages.yml` on every push to `main` that touches `site/`.

- Vanilla HTML, CSS and JavaScript with no build step and no external dependencies
  (no fonts, no CDN scripts), matching the Fleet Console's "no Node on the VM" rule.
- The product icon set is a copy of the console's `icons.js` (Simple Icons, CC0,
  embedded inline).
- `site/assets/topology.js` renders the same topology the console shows and replays
  the canonical "raise a P1" sequence; the walkthrough, overview loop and console
  mock all drive this one engine so the pages cannot disagree with each other.
- Pages: overview, how it works (stepped walkthrough with caller toggle),
  architecture (layers, token propagation, gateway RBAC), cognition (skills),
  scenarios (animated sparklines), Fleet Console, decisions (ADR index), get started.
- Content mirrors `docs/`; `docs/` remains the source of truth. Numbers quoted on the
  site (latency, cost, confidence) come from real runs recorded in the session that
  built them and must be refreshed when the models or skills change.

## Consequences

- Publishing is automatic; the repository's Pages source must be set to
  "GitHub Actions" (the workflow's `configure-pages` step enables it on first run).
- Any change to names, ports, roles, scenarios or ADRs must be reflected on the site
  in the same change, as with `docs/contracts.md`.
- No analytics, no cookies, no third-party requests: the site is safe to show in a
  locked-down corporate browser and works offline once loaded.

## Alternatives considered

- Jekyll / MkDocs rendering `docs/` directly — faithful, but no animation, and a
  build toolchain to maintain.
- Serving the Fleet Console itself as the marketing page — it needs the live cluster.
- A single README — cannot animate the flow, which is the thing executives ask about.
