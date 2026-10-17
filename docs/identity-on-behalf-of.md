# On behalf of: how agents act for a person without becoming that person

This page explains, without assuming any background in authentication, how Maestro and
the domain agents handle the fact that **an agent should not have the same permissions
as the person who asked**. The technical details follow at the end. The decision record
is [ADR-0015](adr/0015-on-behalf-of-token-exchange.md).

## The problem in one picture

A person asks Maestro a question. Maestro has to ask three specialist agents to look
into it. Each agent needs to prove to the fleet gateway, and to itself, that it is
allowed to answer *for that person*.

The naive way is to hand the agents the person's own credentials. In this lab a
credential is a **token**: a signed note from the identity provider (Keycloak) that says
who you are, which doors you may open, and until when. Think of it as a **visitor
badge**.

```
   engineer's badge                      what the cache agent actually needs
   ─────────────────────────             ─────────────────────────────────────
   who:     engineer                     who:     engineer
   doors:   apim, cache                  doors:   cache
   valid:   8 hours                      valid:   a few minutes
   carried by: (nobody says)             carried by: Maestro, for engineer
```

Handing over the person's badge gives the cache agent a door it never needs (apim) for
far longer than it needs it, and leaves no trace that Maestro was the one carrying it.
If that badge is ever copied out of the agent, the copy *is* the engineer, everywhere,
all day.

## What Maestro does instead

1. **Maestro shows Keycloak the caller's badge** and asks: *"Give me a badge on behalf
   of this person, for this one agent."*
2. **Keycloak checks the person really holds that door.** If they do not, it refuses.
   Maestro cannot borrow a right the caller never had.
3. **Keycloak issues a new badge.** It still names the person, but it is addressed to
   **one agent**, opens **one door**, expires in **five minutes**, and is stamped
   **"carried by Maestro"**.
4. **The gateway reads the door on the badge; the agent checks the badge is addressed to
   it.** Two independent locks. Every finding records who it was for and who carried the
   badge.

This is the OAuth 2.0 *token exchange* standard (RFC 8693). Microsoft Entra calls the
same idea the *on-behalf-of flow*, which is where the name comes from.

```
  engineer ──badge──▶ Maestro ──"on behalf of engineer, for cache-agent"──▶ Keycloak
                                                                              │
                        ┌──────── new badge: engineer · carried by maestro ◀──┘
                        │                    addressed to cache-agent
                        │                    opens: cache · valid 5 min
                        ▼
                  fleet gateway ──▶ cache-agent
```

## What the two badges actually look like

These are real tokens from the lab, trimmed to the claims that matter.

The caller's own badge (`engineer`, obtained from Keycloak by the IDE):

```json
{
  "sub": "dd972d27-…",  "preferred_username": "engineer",
  "azp": "ide-cli",
  "aud": ["maestro", "maestro-gateway"],
  "realm_access": { "roles": ["maestro:ask", "domain:apim", "domain:cache"] },
  "exp": "+8 h"
}
```

The on-behalf-of badge Maestro presents to the cache agent:

```json
{
  "sub": "dd972d27-…",  "preferred_username": "engineer",
  "azp": "maestro",
  "act": { "client_id": "maestro" },
  "aud": "cache-agent",
  "realm_access": { "roles": ["domain:cache"] },
  "scope": "domain-cache email profile",
  "exp": "+300 s"
}
```

Same person (`sub`), narrower badge. `azp` and `act` say who is carrying it. `aud` says
which agent it is for. The roles list shrank to the one door.

## What happens when the person lacks a door

`engineer` does not hold `domain:messaging`. When Maestro asks Keycloak for a messaging
badge on their behalf, Keycloak answers:

```
error: invalid_request — Requested audience not available: messaging-agent
```

Maestro records the refusal, does not call the messaging agent, and the assessment says
`not_consulted: messaging — delegation refused by Keycloak`. In practice the gateway
already hid the messaging tools from this caller, so Maestro never tries; the refusal is
the safety net underneath.

## Why not just use Maestro's own badge?

Maestro has an identity of its own (`maestro`). If it used that to call the agents, the
agents would see "Maestro asked" and nothing else: no person, and therefore no way to
limit what Maestro can do to what *this* person may do. Every caller would get Maestro's
full reach. That is the classic *confused deputy* problem. Maestro's own identity is used
for exactly one thing: proving to Keycloak that it is Maestro asking for the exchange.

## Why there is no second identity provider in the lab

In an enterprise, the person's badge comes from the corporate identity provider (Entra,
Okta, Ping) and the agent platform has its own realm that trusts it. We considered
building that second provider here. It would show where human identity comes from, but
the thing this page explains, delegation and narrowing, happens inside the platform
realm either way, because that is the only place that knows the agents exist. One
Keycloak realm is enough to show it truthfully; the enterprise mapping is one brokering
link away.

## See it for yourself

- **Fleet Console → Identity** (button in the top bar): pick a person and an agent and
  press *Ask Keycloak for a badge*. The console performs a real exchange and shows both
  badges, or Keycloak's refusal. Raise an incident and click the **Keycloak** box: each
  delegation Maestro performed is there, with the request it sent.
- **Incident intake → Delegation**: raise the same P1 with *On behalf of* and with
  *Passthrough* and compare what each agent received (click an agent box).
- **Terminal:** `make obo-demo USER_ID=engineer DOMAIN=messaging` prints the same
  exchange in plain language. `make smoke` proves the exact claims on every build.

## Technical appendix

**Keycloak realm (`deploy/keycloak/realm.json`).** Client `maestro`: confidential,
`standard.token.exchange.enabled=true`, `fullScopeAllowed=false`,
`access.token.lifespan=300`, optional client scopes `domain-apim`, `domain-cache`,
`domain-messaging`, hardcoded-claim mapper `act={"client_id":"maestro"}`. Each
`domain-<d>` client scope has an audience mapper for client `<d>-agent` and a realm-role
scope mapping to `domain:<d>`. Clients `apim-agent`, `cache-agent`, `messaging-agent`
are bearer-only (they exist to be audiences). Clients `ide-cli` and `fleet-console` add
`aud: maestro` to their tokens, because Keycloak only exchanges a subject token that
names the requesting client as an audience.

**The exchange request** (Maestro → Keycloak token endpoint, form-encoded):

```
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
client_id=maestro            client_secret=…
subject_token=<caller's access token>
subject_token_type=urn:ietf:params:oauth:token-type:access_token
requested_token_type=urn:ietf:params:oauth:token-type:access_token
audience=cache-agent         scope=domain-cache
```

**Checks on the way down.**

| Where | Check | Effect of an on-behalf-of token |
| --- | --- | --- |
| Fleet gateway `/agents/<d>/mcp` (Maestro's per-agent route) | `jwtAuth`: issuer, signature, `aud` ∈ {`<d>-agent`, maestro-gateway} | a token for another agent is refused at the door |
| Fleet gateway | `mcpAuthorization`: `"domain:<d>" in jwt.realm_access.roles` | only that domain's tools are listed or callable |
| Domain agent | `OIDC_AUDIENCE=<d>-agent,maestro-gateway`: `aud` must contain one of them | a token for another agent is refused |
| Domain agent | records `caller.sub`, `caller.azp`, `caller.act`, `caller.delegated`, `caller.aud` in the Finding | chain of custody in every result |

**Code.** `agents/common/maestro_common/auth.py` (`exchange_token`, `token_summary`),
`agents/maestro/federation.py` (`_token_for`, the only place that decides which token to
present), `agents/maestro/app.py` (`/api/delegate`, the sandbox endpoint),
`agents/fleet-console/app.py` (`/api/identity/try`). Modes: `MAESTRO_AUTH_MODE`
(`exchange` default, `passthrough` legacy), overridable per request with `auth_mode`.

**Events.** `token.exchanged` (edge maestro → keycloak; detail `request`, `subject`,
`issued`, `target`) and `token.refused` (detail `request`, `subject`, `error`,
`error_description`, `target`). Raw tokens are never emitted.
