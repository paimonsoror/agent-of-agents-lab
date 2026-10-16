# 0002. Run the whole ecosystem in KIND on a single VM

Date: 2026-10-15
Status: Accepted

## Context

The demo must build and tear down identically across labs. The target host is one
Linux VM (16 cores, 15 GiB RAM) with Docker. An enterprise would run these components
on Kubernetes, and the executive audience should recognise the shape (namespaces per
domain, Helm releases, ServiceMonitors).

## Decision

A single-node KIND cluster named `maestro` hosts everything. Fixed host ports
(30080–30085) are mapped to NodePorts in the KIND config so URLs are stable and need
no DNS. Third-party components are installed with their upstream Helm charts
(kube-prometheus-stack, agentgateway-standalone); first-party components and the
simple platforms (Keycloak, Valkey, Kafka) live in one Helm chart, `deploy/charts/maestro`.
Images are built on the VM and loaded with `kind load docker-image`.

## Consequences

- One `kind delete cluster` removes everything; nothing leaks onto the host.
- Namespaces mirror enterprise domain boundaries, which makes the story legible.
- RAM is the constraint: Alertmanager is disabled, Prometheus retention is short,
  Kafka runs a single KRaft node with a small heap. Budget is documented in
  `docs/runbook.md`.
- No DNS: Keycloak's issuer is `http://$HOST_IP:30082/realms/maestro` and must be
  consistent inside and outside the cluster (see ADR-0005).

## Alternatives considered

- Docker Compose — faster to start, but hides the Kubernetes shape executives expect
  and complicates per-domain isolation and RBAC for the APIM agent's config reads.
- k3s/k3d — fine, but KIND was requested and is the most common lab tool.
- Multi-node KIND — no benefit for the demo, more RAM.
