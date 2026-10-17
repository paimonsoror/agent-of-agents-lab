# 0015. Maestro presents on-behalf-of tokens obtained by token exchange

Date: 2026-10-16
Status: Accepted. Supersedes the *token propagation* decision of [0005](0005-keycloak-identity-and-token-propagation.md); the Keycloak decisions in 0005 still stand.

## Context

ADR-0005 made Maestro forward the caller's own JWT to every domain agent. That gave
end-to-end authorisation per caller and stopped Maestro escalating, but it has a cost
that becomes obvious once you ask "what does the *agent* hold?":

- The agent receives a badge that opens **every** domain the caller holds, for the full
  token lifetime (8 h in the lab), even though it only ever needs its own domain for
  the next minute.
- Nothing in that token says Maestro carried it. A finding records the caller, but the
  chain "engineer → Maestro → cache-agent" is invisible to the agent and to Keycloak.
- If one agent leaks its bearer token (a log line, a crash dump, a compromised pod), the
  holder *is* the caller, everywhere, all day.

Agents therefore need a credential whose scope is the intersection of three things:
what the caller is entitled to, what the agent being called is for, and what Maestro is
allowed to carry. That is delegation, not propagation. The standard mechanism is the
OAuth 2.0 token exchange grant (RFC 8693), which Keycloak ships as "standard token
exchange" (GA since 26.2). Microsoft Entra calls the same pattern the *on-behalf-of
flow*; the vocabulary carries over.

Verified on the lab's Keycloak 26.8.1 on 2026-10-16: the exchanged token keeps `sub`
(the caller), sets `azp` to the requesting client, honours `audience` and `scope`,
filters realm roles by the requester's scope mappings, uses the requester's own access
token lifespan, and is **refused** ("Requested audience not available") when the caller
lacks the role behind the requested scope. Keycloak does not add an `act` claim by
itself; a hardcoded-claim mapper does.

## Decision

1. **Maestro exchanges, it no longer forwards.** Before every `assess` call Maestro
   trades the caller's token at Keycloak for an on-behalf-of token:
   `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`,
   `subject_token=<caller's token>`, `audience=<domain>-agent`, `scope=domain-<domain>`,
   authenticated as the confidential client `maestro`. The resulting token has
   `sub` = the caller, `azp` = `maestro`, `act = {"client_id": "maestro"}`,
   `aud` = `<domain>-agent` only, `realm_access.roles` = `["domain:<domain>"]` only,
   lifetime **300 s**.
2. **Realm shape** (`deploy/keycloak/realm.json`): client `maestro` is confidential with
   `standard.token.exchange.enabled=true`, `fullScopeAllowed=false`,
   `access.token.lifespan=300`, optional client scopes `domain-apim|cache|messaging`
   and an `act` hardcoded-claim mapper. Each `domain-<d>` scope carries an audience
   mapper for client `<d>-agent` and a realm-role scope mapping to `domain:<d>`. The
   three agents exist as bearer-only clients (audiences). `ide-cli` and `fleet-console`
   tokens additionally carry `aud: maestro`, because Keycloak only exchanges a token
   that names the requester as an audience.
3. **Two locks, one route per agent.** Maestro calls each agent through its own gateway
   route `/agents/<d>/mcp` (single MCP target, audiences `<d>-agent, maestro-gateway`,
   rule `"domain:<d>" in jwt.realm_access.roles`). The multiplexed `/agents/mcp` route
   stays for discovery and for direct callers; it cannot carry an on-behalf-of token
   because agentgateway opens a session with *every* target on initialize, and the
   other agents rightly refuse a token not addressed to them (verified: the gateway
   returns the upstream 401). Each domain agent accepts `aud` ∈ {its own client id,
   `maestro-gateway`} (`OIDC_AUDIENCE` is now a comma list), so a token minted for
   `cache-agent` is refused by `apim-agent` and by the apim route.
4. **Discovery is unchanged.** `tools/list` still uses the caller's own token: the
   gateway's answer is "what may this person see", which is the question.
5. **Refusal is a first-class outcome.** If Keycloak refuses the exchange, Maestro emits
   `token.refused` and reports the domain as
   `not_consulted: delegation refused by Keycloak: …`. Maestro cannot borrow a right
   the caller never had.
6. **Visible and comparable.** Every exchange emits `token.exchanged` with the subject's
   and the issued token's claims (never the raw tokens); the `request.sent` transport
   detail names the mode; findings record `caller.act` and `caller.delegated`. The
   previous behaviour survives as `MAESTRO_AUTH_MODE=passthrough` (chart value
   `identity.delegation`) and as a per-request `auth_mode` on `/api/ask` and the console's
   incident intake, so the two can be shown side by side. The console's **Identity**
   explainer and `make obo-demo` perform real exchanges on demand.

## Consequences

- An agent now holds a badge for one door, for minutes, that names both the person and
  the carrier. Leaking it is a small, attributable incident instead of a big one.
- One extra Keycloak round-trip per agent call (~20 ms); Keycloak must be reachable from
  Maestro at call time, not only at start. Maestro now holds a client secret (`maestro-secret`,
  public demo value) and uses it *only* to exchange, never to call an agent as itself.
- The realm grows by three bearer-only clients, three client scopes and three scope
  mappings; adding a domain means adding one of each (`docs/adding-a-domain.md`).
- **Import gotcha (verified 2026-10-16):** once a realm export lists `clientScopes`,
  Keycloak's `--import-realm` no longer creates its built-in scopes (`roles`, `profile`,
  `basic`, …), and tokens silently lose `realm_access`, `preferred_username` and even
  `sub`. `deploy/keycloak/realm.json` therefore lists the built-in scopes explicitly
  (exported from Keycloak 26.8.1, ids stripped) together with
  `defaultDefaultClientScopes` / `defaultOptionalClientScopes`, and each client lists
  its `defaultClientScopes` (an imported client with only `optionalClientScopes` got
  none). Client `description` fields are also capped at 255 characters by the schema.
- **Key rotation gotcha:** the dev-mode Keycloak re-imports into a fresh in-memory
  database on every realm change and mints new signing keys; agentgateway fetches JWKS
  once at start, so every token is then "signed with an unknown key". The fleet
  gateway's pod annotation therefore includes the realm checksum, so a realm change
  rolls the gateway after Keycloak (its init container waits for the new JWKS).
- The smoke test proves, on every build: the exchanged token's exact claims and lifetime,
  that `engineer → messaging-agent` is refused, and that a cache-agent token lists only
  cache tools at the gateway.
- `not_consulted` has a second reason besides "caller lacks role"; consumers of the
  Assessment schema should not pattern-match the old string.
- No second identity provider is needed to demonstrate delegation (see alternatives). In
  an enterprise the *human* badge comes from the corporate IdP (Entra, Okta) and is
  brokered into the platform realm; the exchange still happens in the platform realm,
  which is the only place that knows the agents.

## Alternatives considered

- **Keep propagation (ADR-0005).** Simplest, but the agent-facing credential is the
  user's whole identity for hours. Kept only as a switchable comparison mode.
- **Maestro calls agents with its own service-account token.** Loses the user entirely:
  the agent cannot tell who it is working for, and Maestro becomes a confused deputy with
  every role. Rejected in 0005 and still rejected.
- **Impersonation (exchanged token with `sub` = maestro, or no `act`).** Indistinguishable
  from Maestro acting alone; the point is the chain of custody. Rejected.
- **A second identity provider** (a `corp` realm or a separate Keycloak, brokered into
  `maestro`). It would show where human identity comes from in an enterprise, but the
  thing to explain, delegation and down-scoping, happens inside the platform realm
  regardless, and brokering adds a browser redirect dance (incompatible with the demo's
  password grant) that teaches nothing about OBO. Documented as the enterprise mapping
  instead of built.
- **Exchange at the gateway** (agentgateway performing the exchange as a backend-auth
  policy). Plausible production shape; rejected for the lab because the exchange would be
  invisible to the console and the carrier would be the gateway, not the agent that
  actually decided to call. Noted as a follow-up once the gateway's policy supports it.
- **Keycloak preview token exchange (v1, external-to-internal).** Preview features are
  not demo-grade; standard (v2) exchange covers the internal case we need.
- **Client roles per agent instead of realm roles + scopes.** Also works, but changes the
  role model every CEL rule, doc and skill already uses. Rejected for churn.
