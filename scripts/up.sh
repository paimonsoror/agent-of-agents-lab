#!/usr/bin/env bash
# Builds the whole Maestro fleet from nothing — or converges an existing one (ADR-0012).
# Every step is safe to re-run. Usage: scripts/up.sh   (or: make up [HOST_IP=...])
set -euo pipefail
source "$(dirname "$0")/lib.sh"
need docker; need kind; need kubectl; need helm; need jq; need curl; need python3

HOST_IP="$(detect_host_ip)"; export HOST_IP
load_secrets
log "host ip: $HOST_IP   cluster: $CLUSTER_NAME"

# --- 0. host tuning (KIND + Prometheus + Kafka need inotify headroom) ---------------------
if [[ "$(sysctl -n fs.inotify.max_user_watches)" -lt 524288 ]]; then
  sudo -n sysctl -qw fs.inotify.max_user_watches=524288 fs.inotify.max_user_instances=512 2>/dev/null \
    || warn "could not raise inotify limits (no passwordless sudo?); continuing"
fi

# --- 1. cluster ---------------------------------------------------------------------------
if cluster_exists; then
  log "kind cluster '$CLUSTER_NAME' exists"
else
  log "creating kind cluster '$CLUSTER_NAME' ($KIND_NODE_IMAGE)"
  kind create cluster --name "$CLUSTER_NAME" --config "$REPO_ROOT/deploy/kind/cluster.yaml" --image "$KIND_NODE_IMAGE" --wait 120s
fi
kctl get nodes >/dev/null

# --- 2. shared monitoring (kube-prometheus-stack) ----------------------------------------
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update prometheus-community >/dev/null
log "installing/upgrading kube-prometheus-stack ${KUBE_PROMETHEUS_STACK_VERSION} as '$MONITORING_RELEASE'"
helm upgrade --install "$MONITORING_RELEASE" prometheus-community/kube-prometheus-stack \
  --kube-context "$KUBE_CONTEXT" --version "$KUBE_PROMETHEUS_STACK_VERSION" \
  --namespace "$MONITORING_NS" --create-namespace \
  -f "$REPO_ROOT/deploy/values/kube-prometheus-stack.yaml" \
  --timeout 15m --wait >/dev/null
for crd in servicemonitors.monitoring.coreos.com podmonitors.monitoring.coreos.com; do
  until kctl get crd "$crd" >/dev/null 2>&1; do sleep 2; done
done

# --- 3. first-party images ----------------------------------------------------------------
python3 "$REPO_ROOT/scripts/validate-skills.py" "$REPO_ROOT/skills"
bash "$REPO_ROOT/scripts/build-images.sh"
# shellcheck source=/dev/null
source "$BUILD_DIR/images.env"
# Pods that tried to start before an image was loaded sit in kubelet's pull backoff (up to 5 min);
# recreating them makes the freshly loaded image take effect immediately.
stuck="$(kctl get pods -A --no-headers 2>/dev/null | awk '$4 ~ /ImagePullBackOff|ErrImagePull|ErrImageNeverPull/ {print $1"/"$2}')"
for p in $stuck; do
  log "  restarting pod $p (was waiting for an image)"
  kctl -n "${p%%/*}" delete pod "${p#*/}" --wait=false >/dev/null || true
done

# --- 4. the umbrella chart ----------------------------------------------------------------
dash_args=()
for f in "$REPO_ROOT"/deploy/grafana/*.json; do
  [[ -e "$f" ]] || continue
  name="$(basename "$f" .json)"
  dash_args+=(--set-file "grafana.dashboards.${name}=${f}")
done
log "installing/upgrading maestro chart"
helm upgrade --install maestro "$CHART_DIR" \
  --kube-context "$KUBE_CONTEXT" --namespace maestro --create-namespace \
  --set "hostIp=${HOST_IP}" \
  --set-string "anthropicApiKey=${ANTHROPIC_API_KEY}" \
  --set-file "keycloak.realmJson=${REPO_ROOT}/deploy/keycloak/realm.json" \
  --set "images.domainAgent.tag=${DOMAIN_AGENT_TAG}" \
  --set "images.maestro.tag=${MAESTRO_TAG}" \
  --set "images.fleetConsole.tag=${FLEET_CONSOLE_TAG}" \
  --set "images.memberPortal.tag=${MEMBER_PORTAL_TAG}" \
  --set "thirdParty.agentgateway=cr.agentgateway.dev/agentgateway:${AGENTGATEWAY_IMAGE_TAG}" \
  --set "thirdParty.keycloak=${KEYCLOAK_IMAGE}" \
  --set "thirdParty.valkey=${VALKEY_IMAGE}" \
  --set "thirdParty.redisExporter=${REDIS_EXPORTER_IMAGE}" \
  --set "thirdParty.kafka=${KAFKA_IMAGE}" \
  --set "thirdParty.kafkaExporter=${KAFKA_EXPORTER_IMAGE}" \
  --set "thirdParty.busybox=${BUSYBOX_IMAGE}" \
  "${dash_args[@]}" \
  --timeout 10m >/dev/null

# --- 5. wait for everything ---------------------------------------------------------------
wait_rollout() { # ns name timeout
  log "  waiting for $1/$2"
  kctl -n "$1" rollout status "deploy/$2" --timeout="$3" >/dev/null || { kctl -n "$1" get pods; die "rollout of $1/$2 failed"; }
}
log "waiting for platforms and identity"
wait_rollout maestro-identity keycloak 10m
wait_rollout domain-cache valkey 5m
wait_rollout domain-messaging kafka 10m
log "waiting for gateways, agents, portal and console"
wait_rollout maestro-gateway fleet-gateway 10m
wait_rollout domain-apim edge-gateway 5m
wait_rollout member-portal portal-api 5m
wait_rollout member-portal portal-consumer 5m
wait_rollout member-portal loadgen 5m
wait_rollout domain-apim apim-agent 5m
wait_rollout domain-cache cache-agent 5m
wait_rollout domain-messaging messaging-agent 5m
wait_rollout maestro maestro 5m
wait_rollout maestro fleet-console 5m
wait_rollout domain-cache valkey-exporter 5m
wait_rollout domain-messaging kafka-exporter 5m

# --- 6. baseline ---------------------------------------------------------------------------
# Every build starts from a clean baseline: Helm's three-way merge restores a patched ConfigMap's data
# but not the scenario annotations, so clear scenarios explicitly rather than rely on that (ADR-0011).
bash "$REPO_ROOT/scripts/scenario.sh" clear || warn "could not clear scenarios; run 'make scenario-clear'"

# --- 7. prove it --------------------------------------------------------------------------
bash "$REPO_ROOT/scripts/smoke.sh"
bash "$REPO_ROOT/scripts/urls.sh"
