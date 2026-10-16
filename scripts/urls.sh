#!/usr/bin/env bash
# Prints every URL and credential a presenter needs.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
H="$(detect_host_ip)"
cat <<EOF

  Maestro fleet — ${H}
  ─────────────────────────────────────────────────────────────────────────
  Fleet Console        http://${H}:30080          (press "Raise P1 incident")
  Grafana              http://${H}:30081          admin / maestro-demo (anonymous viewer enabled)
  Keycloak             http://${H}:30082          admin / maestro-demo   realm: maestro
  Fleet gateway UI     http://${H}:30083/ui
  Fleet gateway MCP    http://${H}:30083/agents/mcp   and   http://${H}:30083/maestro/mcp
  Prometheus           http://${H}:30084
  Member portal (edge) http://${H}:30085/api/members/1001

  Human identities     engineer / engineer (no messaging role)   sre-lead / sre-lead (all roles)
  IDE token            make token-engineer   |   make token-sre-lead
  Scenarios            make scenario-apim-bad-route | scenario-cache-pressure | scenario-messaging-lag | scenario-clear

EOF
