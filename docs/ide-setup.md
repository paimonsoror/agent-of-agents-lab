# Using Maestro and the domain agents from an IDE

The "engineer in the IDE" path uses the **same gateway, same agents, same tools** as the
Fleet Console. The only difference is who is asking.

## 1. Get a token

Tokens are issued by Keycloak to a human user. The Makefile wraps the call:

```bash
make token-engineer          # user engineer  (roles: maestro:ask, domain:apim, domain:cache)
make token-sre-lead          # user sre-lead  (all roles)
export TOKEN=$(make -s token-engineer)
```

Under the hood (useful for other tools):

```bash
curl -s -X POST "http://<HOST_IP>:30082/realms/maestro/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=ide-cli -d username=engineer -d password=engineer \
  | jq -r .access_token
```

Tokens last 8 hours.

## 2. Claude Code

Add Maestro as an MCP server (one tool: `ask_maestro`):

```bash
claude mcp add --transport http maestro "http://<HOST_IP>:30083/maestro/mcp" \
  --header "Authorization: Bearer $TOKEN"
```

Or add the domain agents directly (tools `apim_assess`, `cache_assess`, … filtered by
your roles):

```bash
claude mcp add --transport http fleet-agents "http://<HOST_IP>:30083/agents/mcp" \
  --header "Authorization: Bearer $TOKEN"
```

Then in Claude Code: *"Use ask_maestro: is the member portal healthy right now?"* The
Fleet Console animates the request from the **IDE** node.

## 3. Copilot / Cursor / other MCP clients

Any client that supports Streamable HTTP MCP with custom headers works. Example JSON
(Cursor `mcp.json`, VS Code `mcp.json` use the same shape):

```json
{
  "mcpServers": {
    "maestro": {
      "url": "http://<HOST_IP>:30083/maestro/mcp",
      "headers": { "Authorization": "Bearer <TOKEN>" }
    },
    "fleet-agents": {
      "url": "http://<HOST_IP>:30083/agents/mcp",
      "headers": { "Authorization": "Bearer <TOKEN>" }
    }
  }
}
```

The gateway also serves RFC 9728 protected-resource metadata, so clients that implement
MCP OAuth discovery can log in through Keycloak instead of pasting a token.

## 4. What the engineer sees — and doesn't

| Identity | `/maestro/mcp` | `/agents/mcp` tools listed | Maestro's assessment |
| --- | --- | --- | --- |
| `engineer` | `ask_maestro` | `apim_assess`, `apim_health`, `cache_assess`, `cache_health` | messaging listed under `not_consulted: caller lacks role domain:messaging` |
| `sre-lead` | `ask_maestro` | all three domains | all three consulted |
| no / expired token | 401 | 401 | — |

The gateway filters `tools/list` by the roles in the JWT, so an agent you cannot use is
invisible rather than merely refused. Maestro forwards *your* token to the domain agents,
so it cannot see more on your behalf than you could see yourself (ADR-0005).

## 5. Inspecting the gateway

The agentgateway admin UI is at `http://<HOST_IP>:30083/ui` (read-only): routes, targets,
policies, and a CEL playground to test authorization rules against a token.
