# 0012. One idempotent `make up`; one destructive `make down`

Date: 2026-10-15
Status: Accepted

## Context

The demo is shared across labs. Anyone must be able to build it from a clean VM, run
it, tear it down, and rebuild it to the same state, without tribal knowledge.

## Decision

- `make up` → `scripts/up.sh`: every step is a converge-step —
  `kind get clusters | grep -q maestro || kind create cluster …`,
  `helm upgrade --install …`, `kubectl apply -k …`, image build keyed by content
  hash, `kubectl rollout status` waits, then `scripts/smoke.sh`. Re-running after
  success is fast and changes nothing.
- `make down` → `scripts/down.sh`: `kind delete cluster --name maestro`. Optional
  `make clean` also removes the built images.
- `make smoke` proves: Keycloak issues tokens for every principal; the gateway lists
  the expected tools for `sre-lead` and hides `messaging_*` from `engineer`;
  Prometheus has every target up; each agent's `health` succeeds; the console
  serves the UI.
- Versions are pinned in `deploy/versions.env` and `requirements.txt` files.
- The only host-level inputs are Docker, the CLIs (`scripts/bootstrap-host.sh`
  installs them), `~/.maestro/secrets.env`, and optionally `HOST_IP`.
- `make remote-up VM=user@host SSH_KEY=…` rsyncs the repo to the VM and runs the same
  targets there, so workstation and VM paths are identical.

## Consequences

- Labs can trust the Makefile and ignore the internals.
- The first `make up` on a fresh VM takes several minutes (image pulls); subsequent
  runs take seconds.
- Any step that cannot be made idempotent must be redesigned, not special-cased.

## Alternatives considered

- Ansible/Terraform — more tooling to install on the VM for the same outcome.
- Pre-baked VM images — hide how it works; the build *is* the documentation.
