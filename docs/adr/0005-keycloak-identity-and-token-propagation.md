# 0005. Keycloak issues identities; callers' tokens are propagated, not re-minted

Date: 2026-10-15
Status: Accepted; the *token propagation* decision is superseded by [0015](0015-on-behalf-of-token-exchange.md) (Maestro now exchanges the caller's token for a per-agent on-behalf-of token). The Keycloak, roles and defence-in-depth decisions below still stand.

## Context

Every component that calls another must prove who it is. Enterprises have an IdP
(Entra, Okta, Ping); the demo needs an open-source one that mints JWTs for service
accounts (non-human identities) and users, with roles in claims, and that agentgateway
can validate via JWKS.

## Decision

- **Keycloak 26** in dev mode with the realm `maestro` imported from
  `deploy/keycloak/realm.json` at start. Realm roles `maestro:ask` and `domain:<x>`
  appear in `realm_access.roles`; an audience mapper adds `aud: maestro-gateway`.
- **Non-human identities are OAuth clients with service accounts** (`fleet-console`,
  `maestro`). Humans are realm users (`engineer`, `sre-lead`). Demo credentials are
  public and listed in `docs/contracts.md`.
- **Token propagation.** Maestro forwards the caller's bearer token when it calls the
  domain agents through the gateway. Maestro's own identity is never used to reach a
  domain agent, so a caller can never see more through Maestro than they could see
  directly. The gateway's RBAC therefore applies per end caller.
- **Defence in depth.** Domain agents and Maestro verify the JWT themselves (issuer,
  audience, signature via JWKS) using the MCP SDK's `TokenVerifier`, and record the
  caller (`sub`, `azp`) in every finding and event.
- **One issuer URL.** Keycloak runs with `KC_HOSTNAME=http://$HOST_IP:30082` so the
  `iss` claim is identical whether a token was fetched from inside the cluster or from
  an engineer's laptop.

## Consequences

- The RBAC demo is crisp: user `engineer` lacks `domain:messaging`, so the messaging
  agent is invisible to them and Maestro reports it as "not consulted".
- Token lifetime is 8 h so IDE sessions do not expire mid-demo.
- Token *exchange* (RFC 8693, agentgateway supports it) is the production-grade
  successor to passthrough: Maestro would exchange the caller's token for a
  down-scoped one per domain. Not needed for the demo; noted for the next ADR.
- No TLS in the lab; the design places TLS at the gateway.

## Alternatives considered

- Dex / Zitadel / Ory — lighter, but Keycloak's realm import, service accounts and
  recognisability to an enterprise audience won.
- Maestro minting its own token per downstream call — breaks end-to-end
  authorisation and makes Maestro a confused deputy.
- Static API keys — no identity, no roles, nothing to demonstrate.
