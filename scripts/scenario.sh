#!/usr/bin/env bash
# Fault injection (ADR-0011). The Fleet Console performs the identical Kubernetes operations.
# Usage: scripts/scenario.sh apim-bad-route|cache-pressure|messaging-lag|clear|status
set -euo pipefail
source "$(dirname "$0")/lib.sh"
need kubectl; need python3

CM_NS=domain-apim; CM=edge-gateway-config
GOOD_HOST="portal-api.member-portal:8000"; BAD_HOST="portal-api-v2.member-portal:8000"
CHANGE_ID="CHG0123"

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Replace the route host inside the ConfigMap's config.yaml and set annotations in one patch.
patch_edge() { # $1=from $2=to $3=json-annotations
  local cfg
  cfg="$(kctl -n "$CM_NS" get cm "$CM" -o json | python3 -c "
import json,sys
cm=json.load(sys.stdin); print(cm['data']['config.yaml'].replace('$1','$2'), end='')")"
  python3 - "$cfg" "$3" <<'EOF' | kctl -n "$CM_NS" patch cm "$CM" --type merge -p "$(cat)"
import json,sys
print(json.dumps({"data": {"config.yaml": sys.argv[1]}, "metadata": {"annotations": json.loads(sys.argv[2])}}))
EOF
}

apim_apply() {
  log "apim-bad-route: repointing /api/members to $BAD_HOST as change $CHANGE_ID"
  patch_edge "$GOOD_HOST" "$BAD_HOST" "$(jq -nc --arg t "$(now)" '{"maestro.io/change-id":"'"$CHANGE_ID"'","maestro.io/change-summary":"Route /api/members repointed to portal-api-v2 (canary cut-over)","maestro.io/changed-at":$t,"maestro.io/changed-by":"platform-apim-bot"}')"
  log "the edge gateway reloads within ~60s (kubelet ConfigMap sync)"
}
apim_clear() {
  log "apim-bad-route: rolling back $CHANGE_ID"
  patch_edge "$BAD_HOST" "$GOOD_HOST" "$(jq -nc --arg t "$(now)" '{"maestro.io/change-id":null,"maestro.io/change-summary":null,"maestro.io/changed-at":null,"maestro.io/changed-by":null,"maestro.io/last-rollback":"'"$CHANGE_ID"'","maestro.io/rolled-back-at":$t}')"
}
apim_active() { kctl -n "$CM_NS" get cm "$CM" -o jsonpath='{.metadata.annotations.maestro\.io/change-id}' | grep -q .; }

cache_apply() {
  log "cache-pressure: starting cache-filler job"
  kctl apply -f "$REPO_ROOT/deploy/scenarios/cache-filler.yaml" >/dev/null
}
cache_clear() {
  log "cache-pressure: removing filler and flushing"
  kctl -n domain-cache delete job cache-filler --ignore-not-found --wait=true >/dev/null
  kctl -n domain-cache delete job cache-flush --ignore-not-found --wait=true >/dev/null
  kctl apply -f "$REPO_ROOT/deploy/scenarios/cache-flush.yaml" >/dev/null
  kctl -n domain-cache wait --for=condition=complete job/cache-flush --timeout=120s >/dev/null || warn "flush job did not complete"
  kctl -n domain-cache delete job cache-flush --ignore-not-found >/dev/null
}
cache_active() { kctl -n domain-cache get job cache-filler >/dev/null 2>&1; }

msg_apply() { log "messaging-lag: scaling portal-consumer to 0"; kctl -n member-portal scale deploy/portal-consumer --replicas=0 >/dev/null; }
msg_clear() { log "messaging-lag: scaling portal-consumer to 1"; kctl -n member-portal scale deploy/portal-consumer --replicas=1 >/dev/null; }
msg_active() { [[ "$(kctl -n member-portal get deploy portal-consumer -o jsonpath='{.spec.replicas}')" == "0" ]]; }

status() {
  printf '%-16s %s\n' apim-bad-route "$(apim_active && echo ACTIVE || echo inactive)"
  printf '%-16s %s\n' cache-pressure "$(cache_active && echo ACTIVE || echo inactive)"
  printf '%-16s %s\n' messaging-lag "$(msg_active && echo ACTIVE || echo inactive)"
}

case "${1:-}" in
  apim-bad-route) apim_active && log "already active" || apim_apply ;;
  cache-pressure) cache_active && log "already active" || cache_apply ;;
  messaging-lag)  msg_active && log "already active" || msg_apply ;;
  clear)
    apim_active && apim_clear || true
    cache_active && cache_clear || true
    msg_active && msg_clear || true
    log "all scenarios cleared" ;;
  status) status ;;
  *) die "usage: $0 apim-bad-route|cache-pressure|messaging-lag|clear|status" ;;
esac
