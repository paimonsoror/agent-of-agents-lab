# Fault-injection scenarios

See ADR-0011. Applied and cleared by `scripts/scenario.sh` (Makefile `scenario-*` targets)
and by the Fleet Console (`POST/DELETE /api/scenarios/{name}`), which perform exactly the
same Kubernetes operations:

| Name | Apply | Clear | Active when |
| --- | --- | --- | --- |
| `apim-bad-route` | ConfigMap `domain-apim/edge-gateway-config`: replace `portal-api.member-portal:8000` with `portal-api-v2.member-portal:8000` in `config.yaml`; annotate `maestro.io/change-id=CHG0123`, `maestro.io/change-summary`, `maestro.io/changed-at`, `maestro.io/changed-by=platform-apim-bot` | reverse the replacement; remove `maestro.io/change-id`; annotate `maestro.io/last-rollback=CHG0123`, `maestro.io/rolled-back-at` | annotation `maestro.io/change-id` present |
| `cache-pressure` | `kubectl apply -f cache-filler.yaml` | delete Job `cache-filler`; apply `cache-flush.yaml`, wait, delete it | Job `cache-filler` exists |
| `messaging-lag` | scale `member-portal/deploy/portal-consumer` to 0 | scale to 1 | `spec.replicas == 0` |

The edge gateway watches its mounted config and reloads within about a minute of the
ConfigMap change (kubelet sync). `make up` clears all scenarios explicitly (every build starts
from the baseline); otherwise clear with `make scenario-clear` or the console.
