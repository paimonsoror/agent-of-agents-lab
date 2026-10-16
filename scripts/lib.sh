#!/usr/bin/env bash
# Shared helpers for scripts/*.sh. Source it; do not execute.
# shellcheck disable=SC2034

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER_NAME="maestro"
KUBE_CONTEXT="kind-${CLUSTER_NAME}"
BUILD_DIR="${REPO_ROOT}/.build"
SECRETS_FILE="${MAESTRO_SECRETS_FILE:-${HOME}/.maestro/secrets.env}"
CHART_DIR="${REPO_ROOT}/deploy/charts/maestro"
MONITORING_NS="maestro-monitoring"
MONITORING_RELEASE="monitoring"

# shellcheck source=../deploy/versions.env
set -a; source "${REPO_ROOT}/deploy/versions.env"; set +a

log()  { printf '\033[1;34m[maestro]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[maestro]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[maestro]\033[0m %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1 (run scripts/bootstrap-host.sh)"; }

detect_host_ip() {
  if [[ -n "${HOST_IP:-}" ]]; then echo "$HOST_IP"; return; fi
  local ip
  ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  [[ -n "$ip" ]] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -n "$ip" ]] || die "could not detect HOST_IP; pass HOST_IP=<lan ip>"
  echo "$ip"
}

cluster_exists() { kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; }

kctl() { kubectl --context "$KUBE_CONTEXT" "$@"; }

load_secrets() {
  [[ -f "$SECRETS_FILE" ]] || die "secrets file not found: $SECRETS_FILE
Create it with:
  mkdir -p \"$(dirname "$SECRETS_FILE")\" && chmod 700 \"$(dirname "$SECRETS_FILE")\"
  echo 'ANTHROPIC_API_KEY=sk-ant-...' > \"$SECRETS_FILE\" && chmod 600 \"$SECRETS_FILE\""
  set -a; source "$SECRETS_FILE"; set +a
  [[ -n "${ANTHROPIC_API_KEY:-}" ]] || die "ANTHROPIC_API_KEY is empty in $SECRETS_FILE"
}

# Keycloak helpers used by smoke/urls/Makefile token targets
token_client_credentials() { # $1=client_id $2=secret
  curl -sS --fail -X POST "http://$(detect_host_ip):30082/realms/maestro/protocol/openid-connect/token" \
    -d grant_type=client_credentials -d "client_id=$1" -d "client_secret=$2" | jq -r .access_token
}
token_password() { # $1=username $2=password
  curl -sS --fail -X POST "http://$(detect_host_ip):30082/realms/maestro/protocol/openid-connect/token" \
    -d grant_type=password -d client_id=ide-cli -d "username=$1" -d "password=$2" | jq -r .access_token
}
