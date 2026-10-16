#!/usr/bin/env bash
# Installs the CLIs the build needs on a Debian/Ubuntu-family host. Idempotent: skips what exists.
# Docker itself is a prerequisite (and the user must be in the docker group).
set -euo pipefail
source "$(dirname "$0")/lib.sh"

ARCH="$(uname -m)"; case "$ARCH" in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; esac
KIND_VERSION="${KIND_VERSION:-v0.30.0}"
HELM_VERSION="${HELM_VERSION:-v3.19.0}"

command -v docker >/dev/null || die "docker is required: https://docs.docker.com/engine/install/"
docker info >/dev/null 2>&1 || die "docker is installed but not usable by $(whoami); add the user to the docker group"

SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo -n"

# Docker 29+ builds with BuildKit only; the buildx CLI plugin is a separate package.
if ! docker buildx version >/dev/null 2>&1; then
  log "installing docker buildx plugin"
  if command -v apt-get >/dev/null && $SUDO apt-get install -y -qq docker-buildx >/dev/null 2>&1; then :; else
    BUILDX_VERSION="${BUILDX_VERSION:-v0.30.1}"
    mkdir -p "$HOME/.docker/cli-plugins"
    curl -sSLo "$HOME/.docker/cli-plugins/docker-buildx" \
      "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${ARCH}"
    chmod +x "$HOME/.docker/cli-plugins/docker-buildx"
  fi
fi

if command -v apt-get >/dev/null; then
  pkgs=(); for p in make rsync jq curl python3 python3-venv git; do command -v "$p" >/dev/null || pkgs+=("$p"); done
  if ((${#pkgs[@]})); then log "installing ${pkgs[*]}"; $SUDO apt-get update -qq; $SUDO apt-get install -y -qq "${pkgs[@]}"; fi
fi

if ! command -v kind >/dev/null; then
  log "installing kind $KIND_VERSION"
  curl -sSLo /tmp/kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${ARCH}"
  $SUDO install -m755 /tmp/kind /usr/local/bin/kind
fi
if ! command -v kubectl >/dev/null; then
  v="$(curl -sSL https://dl.k8s.io/release/stable.txt)"
  log "installing kubectl $v"
  curl -sSLo /tmp/kubectl "https://dl.k8s.io/release/${v}/bin/linux/${ARCH}/kubectl"
  $SUDO install -m755 /tmp/kubectl /usr/local/bin/kubectl
fi
if ! command -v helm >/dev/null; then
  log "installing helm $HELM_VERSION"
  curl -sSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" | tar xz -C /tmp
  $SUDO install -m755 "/tmp/linux-${ARCH}/helm" /usr/local/bin/helm
fi

# KIND needs more inotify headroom than most distros ship with.
if [[ "$(sysctl -n fs.inotify.max_user_watches)" -lt 524288 ]]; then
  $SUDO sysctl -qw fs.inotify.max_user_watches=524288 fs.inotify.max_user_instances=512 || warn "could not raise inotify limits"
fi

log "host ready: $(kind version | cut -d' ' -f1-2), $(kubectl version --client 2>/dev/null | head -1), $(helm version --short)"
