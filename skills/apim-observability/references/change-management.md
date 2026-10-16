# Change management on the edge gateway

The edge gateway's configuration is the ConfigMap `edge-gateway-config` (namespace
`domain-apim`, key `config.yaml`). The platform's change process stamps every modification
with annotations; the gateway watches the mounted file and reloads within about a minute.

## Annotations

| Annotation | Meaning |
| --- | --- |
| `maestro.io/change-id` | The change record (e.g. `CHG0123`). Present while the change is live and not rolled back. |
| `maestro.io/change-summary` | One line describing the intent (e.g. "Route /api/members repointed to portal-api-v2 (canary)") |
| `maestro.io/changed-at` | RFC 3339 timestamp of the change |
| `maestro.io/changed-by` | Principal that applied it |
| `maestro.io/last-rollback` | The change id that was most recently rolled back |
| `maestro.io/rolled-back-at` | When |

`get_edge_change_history()` returns these as a dictionary plus the ConfigMap's
`resourceVersion`. Absence of `change-id` means no pending change.

## Correlating a change with a symptom

1. Take `changed-at`.
2. Run the 5xx ratio as a 30-minute range query and find the sample where it first exceeds
   1%. Prometheus samples every 15 s; the gateway reload adds up to ~60 s.
3. If the rise is within **0 to 3 minutes after** `changed-at`, the correlation is strong.
   If the rise is **before** the change, the change is not the cause — say so and keep
   looking.
4. Read the summary: does what it describes explain the symptom? "Repointed to
   portal-api-v2" + 503s on that route = yes.
5. Confirm with `get_edge_routes()`: the route's backend should match the summary.

## What a rollback looks like

After a human rolls back, `change-id` disappears, `last-rollback` names it, the route's
backend returns to `portal-api.member-portal:8000`, and the 5xx ratio falls to ~0 within
two minutes. If you are asked to assess after a rollback, report APIM as cleared and cite
`last-rollback` as the explanation for the earlier symptom.

## Wording recommendations

- Name the change id, the route, and the ConfigMap. A responder should be able to act
  without asking you where.
- Do not say "revert the config"; say "roll back change CHG0123".
- Add a verification step with a concrete query or probe.
