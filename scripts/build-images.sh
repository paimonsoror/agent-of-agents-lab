#!/usr/bin/env bash
# Builds the first-party images and loads them into the KIND cluster.
# Tags are the first 12 hex chars of a sha256 over the build inputs, so an unchanged service is a
# no-op and a changed one rolls out automatically (ADR-0012). Writes .build/images.env.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
need docker; need kind; need sha256sum; need tar

SERVICES=(domain-agent maestro fleet-console member-portal)
mkdir -p "$BUILD_DIR"
: > "$BUILD_DIR/images.env"

content_tag() { # $1=service
  tar -cf - --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
    -C "$REPO_ROOT" "agents/common" "agents/$1" "skills" 2>/dev/null | sha256sum | cut -c1-12
}

image_in_cluster() { # $1=image:tag  (crictl images -q ignores a non-matching filter, so inspect by exact ref)
  cluster_exists && docker exec "${CLUSTER_NAME}-control-plane" crictl inspecti "docker.io/$1" >/dev/null 2>&1
}

for svc in "${SERVICES[@]}"; do
  dockerfile="$REPO_ROOT/agents/$svc/Dockerfile"
  [[ -f "$dockerfile" ]] || die "missing $dockerfile"
  tag="$(content_tag "$svc")"
  image="maestro/${svc}:${tag}"
  if docker image inspect "$image" >/dev/null 2>&1; then
    log "image $image present (unchanged)"
  else
    log "building $image"
    DOCKER_BUILDKIT=1 docker build -q -f "$dockerfile" -t "$image" \
      --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" "$REPO_ROOT" >/dev/null
  fi
  if cluster_exists; then
    if image_in_cluster "$image"; then
      log "  already loaded into kind"
    else
      log "  loading into kind"
      kind load docker-image "$image" --name "$CLUSTER_NAME" >/dev/null
    fi
  fi
  var="$(echo "$svc" | tr 'a-z-' 'A-Z_')_TAG"
  echo "${var}=${tag}" >> "$BUILD_DIR/images.env"
done
log "image tags written to $BUILD_DIR/images.env"
