# Maestro — an agent of agents for observability.
# Run on the build host (Linux VM with Docker) or drive a VM from a workstation with remote-*.
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

VM        ?= oem@192.168.3.221
SSH_KEY   ?= $(HOME)/.ssh/truenas_vm
REMOTE_DIR ?= maestro-fleet
export VM SSH_KEY REMOTE_DIR HOST_IP

.PHONY: help up down reset clean build smoke status urls validate-skills \
        scenario-apim-bad-route scenario-cache-pressure scenario-messaging-lag scenario-clear scenario-status \
        token-engineer token-sre-lead token-console obo-demo bootstrap

help: ## Show this help
	@awk 'BEGIN{FS=":.*##"; printf "\nUsage: make <target> [HOST_IP=x.x.x.x]\n\n"} /^[a-zA-Z0-9_%-]+:.*##/ {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2} /^##@/ {printf "\n%s\n", substr($$0,5)}' $(MAKEFILE_LIST)
	@echo

##@ Build and run (on the host)
bootstrap: ## Install kind/kubectl/helm/jq on this host if missing
	@bash scripts/bootstrap-host.sh
up: ## Build or converge the whole fleet (idempotent), then smoke test
	@bash scripts/up.sh
down: ## Delete the kind cluster (images are kept)
	@bash scripts/down.sh
clean: ## Delete the cluster and the built images
	@bash scripts/down.sh --clean
reset: down up ## Tear down and rebuild
build: ## Build/load first-party images only
	@bash scripts/build-images.sh
smoke: ## Prove the running fleet is healthy
	@bash scripts/smoke.sh
status: ## Pods across every maestro namespace + scenario state
	@kubectl --context kind-maestro get pods -A 2>/dev/null | grep -E '^(NAMESPACE|maestro|domain-|member-portal)' || echo "cluster not running"
	@echo; bash scripts/scenario.sh status 2>/dev/null || true
urls: ## Print URLs and credentials
	@bash scripts/urls.sh
validate-skills: ## Validate skills/ against the agentskills.io spec
	@python3 scripts/validate-skills.py skills

##@ Fault injection (ADR-0011)
scenario-apim-bad-route: ## Break the edge route for /api/members (change CHG0123)
	@bash scripts/scenario.sh apim-bad-route
scenario-cache-pressure: ## Fill Valkey past maxmemory
	@bash scripts/scenario.sh cache-pressure
scenario-messaging-lag: ## Stop the portal consumer so Kafka lag grows
	@bash scripts/scenario.sh messaging-lag
scenario-clear: ## Clear every scenario
	@bash scripts/scenario.sh clear
scenario-status: ## Show which scenarios are active
	@bash scripts/scenario.sh status

##@ Tokens for IDE / curl (printed to stdout)
token-engineer: ## JWT for user engineer (no messaging role)
	@source scripts/lib.sh && token_password engineer engineer
token-sre-lead: ## JWT for user sre-lead (all roles)
	@source scripts/lib.sh && token_password sre-lead sre-lead
token-console: ## JWT for the fleet-console service account
	@source scripts/lib.sh && token_client_credentials fleet-console fleet-console-secret
obo-demo: ## Show an on-behalf-of token exchange in plain language (USER=engineer DOMAIN=apim)
	@bash scripts/obo-demo.sh "$${USER_ID:-engineer}" "$${DOMAIN:-apim}"

##@ Logs
logs-%: ## Tail logs, e.g. make logs-maestro, logs-cache-agent, logs-fleet-gateway
	@ns=$$(kubectl --context kind-maestro get deploy -A -o json | jq -r '.items[] | select(.metadata.name=="$*") | .metadata.namespace' | head -1); \
	 [ -n "$$ns" ] || { echo "no deployment named $*"; exit 1; }; \
	 kubectl --context kind-maestro -n $$ns logs deploy/$* -f --tail=200

##@ Remote (from a workstation; rsyncs the repo to $(VM):$(REMOTE_DIR) then runs the target there)
remote-%: ## e.g. make remote-up VM=user@host SSH_KEY=~/.ssh/key
	@bash scripts/remote.sh $*
