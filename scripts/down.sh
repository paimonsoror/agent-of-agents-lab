#!/usr/bin/env bash
# Removes the whole fleet. Only Docker's image cache survives (`make clean` removes that too).
set -euo pipefail
source "$(dirname "$0")/lib.sh"
need kind

if cluster_exists; then
  log "deleting kind cluster '$CLUSTER_NAME'"
  kind delete cluster --name "$CLUSTER_NAME"
else
  log "kind cluster '$CLUSTER_NAME' does not exist; nothing to delete"
fi
rm -rf "$BUILD_DIR"

if [[ "${1:-}" == "--clean" ]]; then
  log "removing built images"
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^maestro/' | xargs -r docker rmi -f >/dev/null || true
fi
log "done"
