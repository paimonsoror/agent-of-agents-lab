#!/usr/bin/env bash
# Drive a remote build host from a workstation: rsync the repo, then run a Makefile target there.
# Usage: scripts/remote.sh <make-target> [VM=user@host] [SSH_KEY=path] [REMOTE_DIR=~/maestro-fleet]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:?usage: remote.sh <make-target>}"
VM="${VM:?set VM=user@host}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
REMOTE_DIR="${REMOTE_DIR:-maestro-fleet}"
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$VM")

"${SSH[@]}" "mkdir -p '$REMOTE_DIR'"
rsync -az --delete -e "ssh -i $SSH_KEY -o BatchMode=yes" \
  --exclude .git --exclude .build --exclude node_modules --exclude '__pycache__' --exclude '.venv' \
  "$REPO_ROOT/" "$VM:$REMOTE_DIR/"
"${SSH[@]}" -t "cd '$REMOTE_DIR' && make $TARGET ${HOST_IP:+HOST_IP=$HOST_IP}"
