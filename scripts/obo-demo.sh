#!/usr/bin/env bash
# Shows, in plain language, what an on-behalf-of (OBO) token exchange does (ADR-0015).
#   scripts/obo-demo.sh [user] [domain]      e.g.  scripts/obo-demo.sh engineer messaging
# user: engineer | sre-lead | fleet-console     domain: apim | cache | messaging
# It performs the same RFC 8693 exchange Maestro performs, using Maestro's public demo client credentials,
# and prints the caller's badge next to the badge Keycloak issues to Maestro for that one agent.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
need curl; need jq

USER_ID="${1:-engineer}"; DOMAIN="${2:-apim}"
case "$DOMAIN" in apim|cache|messaging) ;; *) die "domain must be apim | cache | messaging";; esac
HOST="$(detect_host_ip)"
KC="http://${HOST}:30082/realms/maestro/protocol/openid-connect/token"

claims_of() { echo "$1" | cut -d. -f2 | tr '_-' '/+' | awk '{l=length($0)%4; if(l==2)print $0"=="; else if(l==3)print $0"="; else print $0}' | base64 -d 2>/dev/null; }
show() { # $1=claims json
  jq -r '"  who (sub)        \(.preferred_username // .sub)",
         "  presented by     \(.azp)\(if .act then "   (act: " + .act.client_id + " — acting on the user'"'"'s behalf)" else "" end)",
         "  addressed to     \([.aud] | flatten | join(", "))",
         "  may open         \((.realm_access.roles // []) | join(", "))",
         "  valid for        \(.exp - .iat) s"' <<<"$1"
}

case "$USER_ID" in
  fleet-console) SUBJECT="$(token_client_credentials fleet-console fleet-console-secret)";;
  engineer)      SUBJECT="$(token_password engineer engineer)";;
  sre-lead)      SUBJECT="$(token_password sre-lead sre-lead)";;
  *) die "user must be engineer | sre-lead | fleet-console";;
esac

echo
echo "1. The caller's own badge (what ${USER_ID} holds, and what Maestro receives)"
show "$(claims_of "$SUBJECT")"
echo
echo "2. Maestro asks Keycloak: \"issue me a badge on behalf of ${USER_ID}, for ${DOMAIN}-agent only\""
echo "   grant_type=urn:ietf:params:oauth:grant-type:token-exchange  audience=${DOMAIN}-agent  scope=domain-${DOMAIN}"
resp="$(curl -sS -X POST "$KC" -d client_id=maestro -d client_secret=maestro-secret \
  -d grant_type=urn:ietf:params:oauth:grant-type:token-exchange -d "subject_token=$SUBJECT" \
  -d subject_token_type=urn:ietf:params:oauth:token-type:access_token -d requested_token_type=urn:ietf:params:oauth:token-type:access_token \
  -d "audience=${DOMAIN}-agent" -d "scope=domain-${DOMAIN}")"
echo
if OBO="$(jq -er '.access_token' <<<"$resp" 2>/dev/null)"; then
  echo "3. Keycloak issued the on-behalf-of badge Maestro will present to ${DOMAIN}-agent"
  show "$(claims_of "$OBO")"
  echo
  echo "   Same person, narrower badge: one door, one role, minutes not hours, and it says who is carrying it."
else
  echo "3. Keycloak REFUSED: $(jq -r '.error_description // .error' <<<"$resp")"
  echo
  echo "   ${USER_ID} does not hold domain:${DOMAIN}, so no badge for ${DOMAIN}-agent can be issued on their behalf."
  echo "   Maestro reports the domain as 'not consulted' — it cannot borrow a right the caller never had."
fi
echo
