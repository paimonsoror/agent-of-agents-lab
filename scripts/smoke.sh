#!/usr/bin/env bash
# Proves the fleet is healthy end to end (ADR-0012). Exit code != 0 means the build is not demo-ready.
#  1. Keycloak issues tokens for every principal.
#  2. The fleet gateway authenticates, and filters tools by role: sre-lead sees every *_assess,
#     engineer does not see messaging_assess, no token -> 401.
#  3. Prometheus has every expected scrape job up.
#  4. Every agent, Maestro, the portal and the console answer /healthz.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
need curl; need jq; need kubectl

HOST_IP="$(detect_host_ip)"
KC="http://${HOST_IP}:30082"
GW="http://${HOST_IP}:30083"
PROM="http://${HOST_IP}:30084"
CONSOLE="http://${HOST_IP}:30080"
fail=0
ok()   { printf '  \033[1;32mPASS\033[0m %s\n' "$*"; }
bad()  { printf '  \033[1;31mFAIL\033[0m %s\n' "$*"; fail=1; }

log "smoke: identity"
T_CONSOLE="$(token_client_credentials fleet-console fleet-console-secret || true)"
T_SRE="$(token_password sre-lead sre-lead || true)"
T_ENG="$(token_password engineer engineer || true)"
for p in "fleet-console:$T_CONSOLE" "sre-lead:$T_SRE" "engineer:$T_ENG"; do
  name="${p%%:*}"; tok="${p#*:}"
  if [[ -n "$tok" && "$tok" != "null" ]]; then
    claims="$(echo "$tok" | cut -d. -f2 | tr '_-' '/+' | awk '{l=length($0)%4; if(l==2)print $0"=="; else if(l==3)print $0"="; else print $0}' | base64 -d 2>/dev/null)"
    iss="$(echo "$claims" | jq -r .iss)"; aud="$(echo "$claims" | jq -r '[.aud] | flatten | join(",")')"
    if [[ "$iss" == "${KC}/realms/maestro" ]] && echo "$aud" | grep -q maestro-gateway; then
      ok "token for $name (iss=$iss aud=$aud roles=$(echo "$claims" | jq -c .realm_access.roles))"
    else
      bad "token for $name has iss=$iss aud=$aud (expected iss=${KC}/realms/maestro, aud containing maestro-gateway)"
    fi
  else
    bad "could not obtain token for $name"
  fi
done

# Minimal MCP client over curl: initialize -> notifications/initialized -> tools/list. Handles JSON or SSE replies.
mcp_tools() { # $1=token  -> prints tool names, one per line; empty on auth failure
  local tok="$1" hdrs sid body
  hdrs="$(mktemp)"
  body="$(curl -sS -D "$hdrs" -X POST "${GW}/agents/mcp" \
    -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' -H 'MCP-Protocol-Version: 2025-06-18' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' || true)"
  sid="$(grep -i '^mcp-session-id:' "$hdrs" | awk '{print $2}' | tr -d '\r' || true)"
  rm -f "$hdrs"
  local sid_hdr=(); [[ -n "$sid" ]] && sid_hdr=(-H "Mcp-Session-Id: $sid")
  curl -sS -o /dev/null -X POST "${GW}/agents/mcp" -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' -H 'MCP-Protocol-Version: 2025-06-18' "${sid_hdr[@]}" \
    -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' || true
  curl -sS -X POST "${GW}/agents/mcp" -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' -H 'MCP-Protocol-Version: 2025-06-18' "${sid_hdr[@]}" \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
    | sed -n 's/^data: //p; /^{/p' | jq -r '.result.tools[]?.name' 2>/dev/null | sort -u
}

log "smoke: fleet gateway authentication and role-based tool filtering"
code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "${GW}/agents/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{}')"
[[ "$code" == "401" ]] && ok "no token -> 401" || bad "no token -> $code (expected 401)"
# Right after a rollout the gateway can still hold endpoints of terminated agent pods; retry briefly.
sre_tools=""
for _ in $(seq 1 12); do
  sre_tools="$(mcp_tools "$T_SRE")"
  [[ -n "$sre_tools" ]] && break
  sleep 5
done
eng_tools="$(mcp_tools "$T_ENG")"
for t in apim_assess cache_assess messaging_assess; do
  echo "$sre_tools" | grep -qx "$t" && ok "sre-lead sees $t" || bad "sre-lead does not see $t (saw: $(echo "$sre_tools" | tr '\n' ' '))"
done
echo "$eng_tools" | grep -qx "messaging_assess" && bad "engineer sees messaging_assess (should be filtered)" || ok "engineer cannot see messaging_assess"
echo "$eng_tools" | grep -qx "cache_assess" && ok "engineer sees cache_assess" || bad "engineer does not see cache_assess (saw: $(echo "$eng_tools" | tr '\n' ' '))"

log "smoke: shared monitoring"
# Pods that just rolled take a scrape interval or two to show as 'up'; poll before judging.
expected_jobs=(fleet-gateway edge-gateway valkey-exporter kafka-exporter apim-agent cache-agent messaging-agent maestro fleet-console portal-api)
for _ in $(seq 1 24); do
  targets="$(curl -sS "${PROM}/api/v1/targets?state=active" | jq -r '.data.activeTargets[] | "\(.labels.job) \(.health)"' | sort -u || true)"
  missing=0
  for job in "${expected_jobs[@]}"; do echo "$targets" | grep -q "^${job} up$" || missing=1; done
  [[ $missing -eq 0 ]] && break
  sleep 5
done
for job in "${expected_jobs[@]}"; do
  if echo "$targets" | grep -q "^${job} up$"; then ok "prometheus target $job up"; else bad "prometheus target $job not up ($(echo "$targets" | grep "^${job} " || echo missing))"; fi
done

log "smoke: service health"
check_health() { # ns svc port
  local out
  out="$(kctl -n maestro exec deploy/fleet-console -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://$2.$1:$3/healthz', timeout=5).status)" 2>/dev/null || true)"
  [[ "$out" == "200" ]] && ok "$1/$2 healthz" || bad "$1/$2 healthz -> ${out:-no response}"
}
check_health domain-apim apim-agent 8000
check_health domain-cache cache-agent 8000
check_health domain-messaging messaging-agent 8000
check_health maestro maestro 8000
check_health member-portal portal-api 8000
code="$(curl -sS -o /dev/null -w '%{http_code}' "${CONSOLE}/healthz" || true)"
[[ "$code" == "200" ]] && ok "fleet console reachable at $CONSOLE" || bad "fleet console -> $code"
# The edge gateway re-reads its ConfigMap-mounted config within ~60-90 s of a change (e.g. a scenario
# being cleared by `make up`); give it that long before judging the health route.
# The apim-bad-route scenario breaks both edge routes on purpose, and scenarios survive `make up`
# (ADR-0011), so judge the edge against the scenario state. The gateway re-reads its config within
# ~60-90 s of a change, so poll for the expected code.
if kctl -n domain-apim get configmap edge-gateway-config -o jsonpath='{.metadata.annotations.maestro\.io/change-id}' 2>/dev/null | grep -q .; then
  want=503; why=" (apim-bad-route scenario is active, as expected)"
else
  want=200; why=""
fi
for path in /api/health /api/members/smoke; do
  code=""
  for _ in $(seq 1 20); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' "http://${HOST_IP}:30085${path}" || true)"
    [[ "$code" == "$want" ]] && break
    sleep 5
  done
  [[ "$code" == "$want" ]] && ok "edge gateway ${path} -> ${code}${why}" || bad "edge gateway ${path} -> ${code} (expected ${want}${why})"
done

if [[ $fail -ne 0 ]]; then die "smoke test FAILED"; fi
log "smoke test passed"
