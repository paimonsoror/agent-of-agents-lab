# Runbook

Operating the Maestro fleet in a lab. Design is in `architecture.md`; names and ports in
`contracts.md`; the *why* in `adr/`.

## 1. Prerequisites

| Item | Requirement |
| --- | --- |
| Host | Linux VM, x86_64 or arm64, 8+ cores, **12+ GiB RAM** (sized for 15 GiB), 30 GB free disk |
| Docker | Engine 24+; the build user in the `docker` group |
| CLIs | `kind`, `kubectl`, `helm`, `make`, `jq`, `curl`, `python3`, `rsync` — `make bootstrap` installs the missing ones |
| Network | Outbound HTTPS to pull images (Docker Hub, quay.io, cr.agentgateway.dev, ghcr.io), PyPI, and `api.anthropic.com` |
| Ports | 30080–30085 free on the host |

## 2. Secrets

The only secret is the Anthropic API key. It is read at deploy time and written into a
Kubernetes Secret named `anthropic` in each namespace that runs an LLM loop. It is never
stored in the repo, in Helm values files, or in Helm release history as a file.

```bash
mkdir -p ~/.maestro && chmod 700 ~/.maestro
echo 'ANTHROPIC_API_KEY=sk-ant-...' > ~/.maestro/secrets.env && chmod 600 ~/.maestro/secrets.env
```

Override the location with `MAESTRO_SECRETS_FILE=/path/to/file make up`.

Everything else is a **deliberately public demo credential**:

| Component | Credential |
| --- | --- |
| Keycloak admin | `admin` / `maestro-demo` |
| Grafana | `admin` / `maestro-demo` (anonymous Viewer also enabled) |
| Keycloak client `fleet-console` | secret `fleet-console-secret` |
| Keycloak client `maestro` | secret `maestro-secret` |
| User `engineer` | password `engineer` — roles `maestro:ask`, `domain:apim`, `domain:cache` |
| User `sre-lead` | password `sre-lead` — all roles |

## 3. Build, run, tear down

```bash
make up        # create cluster, install monitoring, build images, install chart, wait, smoke test
make smoke     # re-run the health proof any time
make urls      # print every URL
make down      # delete the cluster
make reset     # down + up
make clean     # down + remove built images
```

From a workstation: `make remote-up VM=user@host SSH_KEY=~/.ssh/key` (rsyncs the repo to
`~/maestro-fleet` on the VM and runs `make up` there). `HOST_IP` is auto-detected on the
host (first LAN IPv4); override with `make up HOST_IP=10.0.0.5` when the VM has several.

First build on a fresh VM: 6–12 minutes (image pulls dominate). Subsequent `make up`:
under a minute when nothing changed.

### What `make up` does (scripts/up.sh)

1. Raises inotify limits (KIND/Prometheus/Kafka need them).
2. `kind create cluster --name maestro` with fixed host-port mappings — skipped if present.
3. `helm upgrade --install monitoring prometheus-community/kube-prometheus-stack` into
   `maestro-monitoring` (Prometheus + Grafana + operator; no Alertmanager).
4. Validates `skills/`, builds the four first-party images tagged by content hash, loads them
   into KIND (`scripts/build-images.sh`). Unchanged inputs ⇒ no rebuild, no reload.
5. `helm upgrade --install maestro deploy/charts/maestro` with the host IP, image tags,
   pinned third-party images, the Keycloak realm (`--set-file`) and every Grafana dashboard
   (`--set-file` per JSON).
6. Waits for every Deployment to roll out, in dependency order.
7. Runs `scripts/smoke.sh` and prints the URLs.

## 4. URLs

| What | URL |
| --- | --- |
| Fleet Console | `http://HOST_IP:30080` |
| Grafana | `http://HOST_IP:30081` |
| Keycloak | `http://HOST_IP:30082` (realm `maestro`; this is also the JWT `iss` base) |
| Fleet gateway | `http://HOST_IP:30083/agents/mcp`, `/maestro/mcp`, admin UI at `/ui` |
| Prometheus | `http://HOST_IP:30084` |
| Member portal via edge gateway | `http://HOST_IP:30085/api/members/1001`, `/api/health` |

## 5. RAM budget (requests → limits)

| Component | Namespace | Memory |
| --- | --- | --- |
| KIND node + kube-system | — | ~1.2 GiB |
| Prometheus | maestro-monitoring | 512 Mi → 1 Gi |
| Grafana + operator + kube-state-metrics + node-exporter | maestro-monitoring | ~300 Mi → 830 Mi |
| Keycloak | maestro-identity | 600 Mi → 1 Gi |
| Kafka (KRaft, 512 Mi heap) | domain-messaging | 768 Mi → 1 Gi |
| Valkey (maxmemory 64 Mi) + exporter | domain-cache | 128 Mi → 290 Mi |
| Two agentgateways | maestro-gateway, domain-apim | 128 Mi → 512 Mi |
| Three domain agents + Maestro | domain-*, maestro | 640 Mi → 2 Gi |
| Fleet Console | maestro | 96 Mi → 256 Mi |
| Member portal (api, consumer, loadgen) | member-portal | 288 Mi → 768 Mi |
| **Total** | | **~4.7 GiB requested, ~8.7 GiB at limits** |

Comfortable on 15 GiB; workable on 12.

## 6. Scenarios (fault injection)

| Make target | Console button | Effect | Signal the agents find |
| --- | --- | --- | --- |
| `scenario-apim-bad-route` | *Bad route change* | Edge gateway ConfigMap: `/api/members` → non-existent `portal-api-v2`, annotated `maestro.io/change-id=CHG0123` | 5xx rate on `edge-gateway`; a recent change on the route; recommendation: roll back CHG0123 |
| `scenario-cache-pressure` | *Cache pressure* | Job `cache-filler` writes past Valkey `maxmemory` continuously | `redis_evicted_keys_total` climbing, hit ratio collapsing |
| `scenario-messaging-lag` | *Consumer outage* | `portal-consumer` scaled to 0 | `kafka_consumergroup_lag` growing for group `portal-consumer` |
| `scenario-clear` | *Clear all* | Reverses all of the above | — |
| `scenario-status` | — | Active state derived from the cluster | — |

Active state is never stored; it is read from the cluster (annotation present / job exists /
replicas = 0), so the console and the CLI always agree. The edge gateway reloads its mounted
config within ~60 s of the ConfigMap patch (kubelet sync interval); allow a minute before
expecting 5xx. `make up` clears all scenarios explicitly before its smoke test, so every build
starts from the baseline; during a demo use the console toggles or `make scenario-clear`.

## 7. Using the agents from an IDE

```bash
TOKEN=$(make -s token-engineer)          # or token-sre-lead
# Claude Code
claude mcp add --transport http maestro http://HOST_IP:30083/maestro/mcp --header "Authorization: Bearer $TOKEN"
claude mcp add --transport http domain-agents http://HOST_IP:30083/agents/mcp --header "Authorization: Bearer $TOKEN"
```

Tokens last 8 hours. `engineer` will not see `messaging_*` tools; `sre-lead` sees everything.
See `ide-setup.md` for Copilot and Cursor.

## 8. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Fleet gateway pod stuck in `Init:0/1` | Keycloak not ready; the gateway exits if it cannot fetch JWKS at start, so an init container waits | `kubectl -n maestro-identity logs deploy/keycloak`; Keycloak takes ~60–90 s on first boot |
| Gateway returns 401 with a valid-looking token | `iss` mismatch: token issuer ≠ `http://HOST_IP:30082/realms/maestro` (wrong `HOST_IP`, or token fetched from a different hostname before `KC_HOSTNAME` applied) | `make smoke` prints the issuer; rebuild with the right `HOST_IP=`; fetch a fresh token |
| Gateway 401 and the token's `aud` lacks `maestro-gateway` | Realm import changed / client missing the audience mapper | `kubectl -n maestro-identity rollout restart deploy/keycloak` re-imports the realm |
| Agent answers `421 Misdirected Request` | MCP SDK DNS-rebinding protection enabled; our `build_app` disables it, so this means a service was started outside `maestro_common.server` | Use `build_app()` |
| `kind create cluster` fails on ports | 30080–30085 in use, or a stale `maestro` container | `docker ps`, `make down`, free the port |
| Pods `ImagePullBackOff` for `maestro/*` | Image built but not loaded into KIND (cluster recreated after build) | `make build` (idempotent) then `make up` |
| Prometheus target `down` for an agent | Agent crash-looped (usually a bad `ANTHROPIC_API_KEY` is *not* checked at start — look for Python tracebacks) | `make logs-cache-agent` |
| Kafka exporter restarts at start | Starts before the broker; it is retried | Wait; `make smoke` |
| Smoke: "engineer sees messaging_assess" | CEL rules edited, or roles changed in the realm | Compare `fleet-gateway-config` ConfigMap with `docs/contracts.md` |
| Everything slow / OOM | VM under 12 GiB | Lower Prometheus limits in `deploy/values/kube-prometheus-stack.yaml`; drop `loadgen` replicas |
| `BuildKit is enabled but the buildx component is missing` | Docker 29+ builds only with BuildKit; the CLI plugin is a separate package | `make bootstrap` (installs `docker-buildx`) |
| `Permission denied` running a script | Exec bit lost (files edited from Windows over `\\wsl.localhost`, or copied without modes) | `chmod +x scripts/*.sh scripts/*.py`; the Makefile invokes scripts via `bash`/`python3` so this only matters for direct calls |
| Maestro/agents emit `error … invalid x-api-key` | The key in `~/.maestro/secrets.env` is wrong or a placeholder | Fix the file and re-run `make up`; the Deployments carry a checksum of the key, so pods roll automatically |

Useful commands: `make status`, `make logs-<deployment>`, `kubectl --context kind-maestro get events -A --sort-by=.lastTimestamp | tail`.

## 9. Teardown

`make down` deletes the KIND cluster and `.build/`. `make clean` also removes the
`maestro/*` images. Nothing else is left on the host except `~/.maestro/secrets.env`,
which you own.

## 10. Production notes (what the demo deliberately skips)

- TLS at the gateway and between services; Keycloak behind TLS with a real hostname.
- The vendor `agentgateway-standalone` Helm chart (`oci://cr.agentgateway.dev/charts/agentgateway-standalone`)
  instead of our plain Deployments; HA replicas; OpenTelemetry tracing to a collector.
- Keycloak with a database and the realm managed by configuration-as-code.
- Prometheus retention and remote write; Loki for logs.
- Token exchange (RFC 8693) instead of passthrough (ADR-0005).
