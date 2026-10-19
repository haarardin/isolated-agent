ifneq (,$(wildcard ./.env))
include .env
export
endif

COMPOSE_PROJECT_NAME ?= isolated-agent-demo
PROJECT_DIR ?= ./workspace
# A canonical-project-path fingerprint prevents state/history/long-term-memory
# from leaking when PROJECT_DIR changes under the same Compose project name.
CODEX_PROJECT_KEY := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --field key)
# Default: host bind directories under the isolated-agent repository root.
# Each base directory receives a source-project fingerprint subdirectory.
# A bare name (no slash) still selects a legacy Podman named volume.
CODEX_STATE_VOLUME ?= ./volumes/codex
CODEX_STATE_MOUNT_TYPE := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind codex --storage "$(CODEX_STATE_VOLUME)" --field mount-type)
CODEX_STATE_MOUNT_SOURCE := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind codex --storage "$(CODEX_STATE_VOLUME)" --field mount-source)
CODEX_NAMED_VOLUME := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind codex --storage "$(CODEX_STATE_VOLUME)" --field named-volume)
# Explicit, one-time opt-in only for a pre-existing, unbound volume.
CODEX_BIND_EXISTING_STATE ?= false
# Explicit opt-in required when a selected named volume does not exist.
CODEX_CREATE_NAMED_VOLUME ?= false
export CODEX_STATE_MOUNT_TYPE CODEX_STATE_MOUNT_SOURCE CODEX_NAMED_VOLUME
AGENT_SUBNET ?= auto
# Independent from COMPOSE_PROJECT_NAME; same value intentionally shares a network.
AGENT_NETWORK_NAME ?= $(COMPOSE_PROJECT_NAME)_isolated-dev
BLOCK_CIDRS ?=
SQUID_IMAGE ?= docker.io/ubuntu/squid:6.6-24.04_edge
export COMPOSE_PROJECT_NAME AGENT_NETWORK_NAME AGENT_SUBNET BLOCK_CIDRS SQUID_IMAGE
PODMAN ?= podman
COMPOSE ?= bash scripts/compose.sh
COMPOSE_WEB ?= $(COMPOSE) -f compose.yaml -f compose.web.yaml -f .generated/compose.tools.yaml
COMPOSE_EXAMPLE ?= $(COMPOSE) -f compose.yaml -f compose.web.yaml -f compose.example-services.yaml -f .generated/compose.tools.yaml
COMPOSE_OFFLINE ?= $(COMPOSE) -f compose.yaml -f .generated/compose.tools.yaml
COMPOSE_TOOLS ?= $(COMPOSE_WEB)
COMPOSE_OFFLINE_EXAMPLE ?= $(COMPOSE) -f compose.yaml -f compose.example-services.yaml -f .generated/compose.tools.yaml

BASE_IMAGE ?= localhost/isolated-agent-base:dev
CODEX_IMAGE ?= localhost/isolated-agent-codex:dev
DEPENDENCIES_IMAGE ?= localhost/isolated-agent-dependencies:dev
PROJECT_IMAGE ?= localhost/isolated-agent-project-$(CODEX_PROJECT_KEY):dev
# Prevent different projects on one host from sharing a baked MCP config image.
export PROJECT_IMAGE

PROJECT_APT_PACKAGES ?=
CODEX_AGENTS_FILE ?= templates/AGENTS.global.md
CODEX_MODEL ?=
CODEX_MODEL_REASONING_EFFORT ?= high
CODEX_PLAN_REASONING_EFFORT ?= high
CODEX_MODEL_VERBOSITY ?=
CODEX_PERSONALITY ?=
CODEX_REVIEW_MODEL ?=
CODEX_SERVICE_TIER ?=
CODEX_FILE_OPENER ?= none
CODEX_APPROVAL_POLICY ?= never
CODEX_SANDBOX_MODE ?= danger-full-access
CODEX_NETWORK_ACCESS ?= true
CODEX_WEB_SEARCH ?= cached
CODEX_PROJECT_DOC_MAX_BYTES ?= 65536
CODEX_SHELL_IGNORE_DEFAULT_EXCLUDES ?= false
CODEX_FEATURE_MEMORIES ?= true

.PHONY: start stop lsp-doctor deps-tool-state deps-validate deps-plan deps-generate deps-build deps-tools-up deps-reconcile deps-lint prepare-state memory-info network-info network-ensure remote-start remote-pair remote-status remote-stop remote-logs remote-doctor network-check network-static prepare-web migrate-network offline offline-example preflight doctor build build-base build-codex build-project ensure-images ensure-base-image ensure-codex-image ensure-project-image test-image-reuse-static test-project-context-static up up-example down down-example stop-agent remove-agent recreate-agent clean reset-example-db login codex shell test race integration logs logs-example ps ps-example reset-state

help:
	@printf '%s\n' \
	  'make preflight      Check host requirements' \
	  'make doctor         Check the running agent toolchain/runtime' \
	  'make build          Build Base, Codex, Dependencies and Project images' \
	  'make deps-plan     Inspect generated tools and MCP configuration' \
	  'make ensure-images  Reuse Base, Codex and Project images; build only missing' \
	  'make test-image-reuse-static Validate image reuse logic without Podman' \
	  'make test-project-context-static Validate /workspace project context rules' \
	  'make up             Start agent with filtered Squid egress' \
	  'make start          Restart only previously running project containers, without recreating' \
	  'make stop           Stop all running containers in this Compose project, preserving them' \
	  'make offline        Start agent without Internet' \
	  'make remote-start   Start headless Codex Remote Control' \
	  'make remote-pair    Show temporary Android pairing code' \
	  'make remote-status  Check managed app-server daemon' \
	  'make remote-stop    Stop Remote Control' \
	  'make remote-doctor  Safe daemon/network diagnostics' \
	  'make network-check Test rootless network isolation' \
	  'make network-info  Inspect assigned project network' \
	  'make memory-info   Show project-scoped persistent volumes (no secrets)' \
	  'make network-ensure Create or reuse the project's internal network' \
	  'make migrate-network CONFIRM=YES   Migrate old network' \
	  'make up-example     Start agent + PostgreSQL + Redis' \
	  'make ps-example     Show agent + example services' \
	  'make stop-agent     Stop only the agent container' \
	  'make remove-agent   Remove only the agent container' \
	  'make recreate-agent Recreate only the agent container' \
	  'make login          Authenticate Codex using device flow' \
	  'make codex          Open interactive Codex CLI' \
	  'make shell          Open a shell inside the agent' \
	  'make test           Run the project unit-test command' \
	  'make race           Run Go race tests' \
	  'make integration    Run project integration tests' \
	  'make logs           Follow compose logs' \
	  'make down           Stop the base agent environment' \
	  'make down-example   Stop agent + example services' \
	  'make clean          Force-clean this Compose project, keep volumes' \
	  'make reset-example-db Delete only example PostgreSQL data' \
	  'make reset-state    Force-clean this Compose project and volumes'

memory-info:
	@printf 'Project path:         %s\n' "$(abspath $(PROJECT_DIR))"
	@printf 'Project key:          %s\n' "$(CODEX_PROJECT_KEY)"
	@printf 'Codex (%s):        %s -> /root/.codex\n' "$(CODEX_STATE_MOUNT_TYPE)" "$(CODEX_STATE_MOUNT_SOURCE)"
	@printf '%s\n' 'Serena project memories remain in PROJECT_DIR/.serena/memories/'

preflight:
	@bash scripts/preflight.sh
	@python3 scripts/network-preflight.py --subnet "$(AGENT_SUBNET)" --project "$(COMPOSE_PROJECT_NAME)" --network-name "$(AGENT_NETWORK_NAME)" --state .state/network.json

network-info:
	@python3 scripts/network-preflight.py --subnet "$(AGENT_SUBNET)" --project "$(COMPOSE_PROJECT_NAME)" --network-name "$(AGENT_NETWORK_NAME)" --state .state/network.json

network-ensure: preflight
	@python3 scripts/network-preflight.py --ensure --subnet "$(AGENT_SUBNET)" --project "$(COMPOSE_PROJECT_NAME)" --network-name "$(AGENT_NETWORK_NAME)" --state .state/network.json

prepare-state:
	@python3 scripts/prepare-state.py --codex-type "$(CODEX_STATE_MOUNT_TYPE)" --codex-source "$(CODEX_STATE_MOUNT_SOURCE)" --codex-named-volume "$(CODEX_NAMED_VOLUME)" --codex-create-named-volume "$(CODEX_CREATE_NAMED_VOLUME)" --podman "$(PODMAN)"

prepare-web: network-ensure prepare-state deps-generate deps-tool-state deps-reconcile
	@bash scripts/prepare-web.sh

deps-validate:
	@python3 scripts/dependencies.py validate

deps-plan:
	@python3 scripts/dependencies.py plan

deps-generate:
	@python3 scripts/dependencies.py generate

deps-tool-state:
	@python3 scripts/dependencies.py tool-state

deps-build: deps-generate
	@python3 scripts/dependencies.py build --engine "$(PODMAN)" --base-image "$(BASE_IMAGE)" --codex-image "$(CODEX_IMAGE)" --deps-image "$(DEPENDENCIES_IMAGE)"

deps-reconcile: deps-generate
	@services="$$(python3 scripts/dependencies.py sidecar-services)"; \
	 PODMAN="$(PODMAN)" python3 scripts/reconcile-tool-sidecars.py --project "$(COMPOSE_PROJECT_NAME)" --enabled "$$services"

deps-tools-up: deps-generate deps-tool-state deps-reconcile
	@services="$$(python3 scripts/dependencies.py sidecar-services)"; \
	if [ -n "$$services" ]; then \
		$(COMPOSE_TOOLS) up -d $$services; \
	else \
		printf 'Agent Tools: no sidecars enabled; skipping Compose sidecar startup.\n'; \
	fi

doctor:
	@bash scripts/doctor.sh

# Deep check: starts Serena's real language servers and queries symbols.
# Run after a project has source files; empty workspace is not a valid LSP probe.
lsp-doctor:
	@bash scripts/compose.sh exec agent bash /usr/local/bin/isolated-agent-tool-lsp-runtime probe

build: build-base build-codex build-project

# Fast bootstrap for additional repository clones on the same rootless-Podman
# host. Podman image storage is shared by tag for the current host user, so
# reuse an existing image instead of invoking a redundant build.
#
# This intentionally checks only image existence. If project-level inputs
# change, use make build-project. Project-specific
# context should normally live under PROJECT_DIR (/workspace) instead.
ensure-images: ensure-project-image

ensure-base-image:
	@if $(PODMAN) image exists "$(BASE_IMAGE)"; then \
		printf 'Reusing existing image: %s\n' "$(BASE_IMAGE)"; \
	else \
		printf 'Image missing, building: %s\n' "$(BASE_IMAGE)"; \
		$(MAKE) build-base; \
	fi

ensure-codex-image: ensure-base-image
	@if $(PODMAN) image exists "$(CODEX_IMAGE)"; then \
		printf 'Reusing existing image: %s\n' "$(CODEX_IMAGE)"; \
	else \
		printf 'Image missing, building: %s\n' "$(CODEX_IMAGE)"; \
		$(MAKE) build-codex; \
	fi

ensure-project-image: ensure-codex-image
	@if $(PODMAN) image exists "$(PROJECT_IMAGE)"; then \
		printf 'Reusing existing image: %s\n' "$(PROJECT_IMAGE)"; \
	else \
		printf 'Image missing, building: %s\n' "$(PROJECT_IMAGE)"; \
		$(MAKE) build-project; \
	fi

test-image-reuse-static:
	@bash scripts/test-image-reuse-static.sh

test-project-context-static:
	@bash scripts/test-project-context-static.sh

build-base:
	$(PODMAN) build \
		-f images/base/Containerfile \
		-t $(BASE_IMAGE) \
		.

build-codex:
	$(PODMAN) build \
		-f images/codex/Containerfile \
		--build-arg BASE_IMAGE="$(BASE_IMAGE)" \
		-t $(CODEX_IMAGE) \
		.

build-project: deps-build
	$(PODMAN) build \
		-f images/project/Containerfile \
		--build-arg DEPENDENCIES_IMAGE="$(DEPENDENCIES_IMAGE)" \
		--build-arg PROJECT_APT_PACKAGES="$(PROJECT_APT_PACKAGES)" \
		--build-arg CODEX_AGENTS_FILE="$(CODEX_AGENTS_FILE)" \
		--build-arg CODEX_MODEL="$(CODEX_MODEL)" \
		--build-arg CODEX_MODEL_REASONING_EFFORT="$(CODEX_MODEL_REASONING_EFFORT)" \
		--build-arg CODEX_PLAN_REASONING_EFFORT="$(CODEX_PLAN_REASONING_EFFORT)" \
		--build-arg CODEX_MODEL_VERBOSITY="$(CODEX_MODEL_VERBOSITY)" \
		--build-arg CODEX_PERSONALITY="$(CODEX_PERSONALITY)" \
		--build-arg CODEX_REVIEW_MODEL="$(CODEX_REVIEW_MODEL)" \
		--build-arg CODEX_SERVICE_TIER="$(CODEX_SERVICE_TIER)" \
		--build-arg CODEX_FILE_OPENER="$(CODEX_FILE_OPENER)" \
		--build-arg CODEX_APPROVAL_POLICY="$(CODEX_APPROVAL_POLICY)" \
		--build-arg CODEX_SANDBOX_MODE="$(CODEX_SANDBOX_MODE)" \
		--build-arg CODEX_NETWORK_ACCESS="$(CODEX_NETWORK_ACCESS)" \
		--build-arg CODEX_WEB_SEARCH="$(CODEX_WEB_SEARCH)" \
		--build-arg CODEX_PROJECT_DOC_MAX_BYTES="$(CODEX_PROJECT_DOC_MAX_BYTES)" \
		--build-arg CODEX_SHELL_IGNORE_DEFAULT_EXCLUDES="$(CODEX_SHELL_IGNORE_DEFAULT_EXCLUDES)" \
		--build-arg CODEX_FEATURE_MEMORIES="$(CODEX_FEATURE_MEMORIES)" \
		-t $(PROJECT_IMAGE) \
		.

# Unlike 'up', these targets do not invoke Compose or change images,
# service profiles, networks, containers or persistent state. The checkpoint
# lives in .state/ and remembers only services running before 'make stop'.
start:
	@PODMAN="$(PODMAN)" python3 scripts/project-lifecycle.py start

stop:
	@PODMAN="$(PODMAN)" python3 scripts/project-lifecycle.py stop

up: prepare-web
	@bash scripts/check-agent-state.sh
	$(COMPOSE_WEB) up -d

up-example: prepare-web
	@bash scripts/check-agent-state.sh
	$(COMPOSE_EXAMPLE) up -d

offline: network-ensure prepare-state deps-generate deps-tool-state deps-reconcile
	@bash scripts/check-agent-state.sh
	@bash scripts/remove-service.sh squid
	@$(MAKE) deps-tools-up COMPOSE_TOOLS="$(COMPOSE_OFFLINE)"
	$(COMPOSE_OFFLINE) up -d agent

offline-example: network-ensure prepare-state deps-generate deps-tool-state deps-reconcile
	@bash scripts/check-agent-state.sh
	@bash scripts/remove-service.sh squid
	$(COMPOSE_OFFLINE_EXAMPLE) up -d

down: deps-generate
	$(COMPOSE_WEB) down

down-example: deps-generate
	$(COMPOSE_EXAMPLE) down

migrate-network:
	@test "$(CONFIRM)" = "YES" || { echo "Set CONFIRM=YES; stop active Codex sessions first"; exit 1; }
	@bash scripts/migrate-network.sh
	@$(MAKE) up

stop-agent: deps-generate
	$(COMPOSE_EXAMPLE) stop agent

remove-agent:
	@bash scripts/remove-service.sh agent

recreate-agent: prepare-web
	@$(MAKE) deps-tools-up
	@bash scripts/remove-service.sh agent
	$(COMPOSE_EXAMPLE) up -d agent

clean:
	@bash scripts/cleanup.sh

reset-example-db:
	@bash scripts/reset-example-db.sh

network-check:
	@bash scripts/network-check.sh

remote-start:
	@bash scripts/remote-control.sh start

remote-pair:
	@bash scripts/remote-control.sh pair

remote-status:
	@bash scripts/remote-control.sh status

remote-stop:
	@bash scripts/remote-control.sh stop

remote-logs:
	@bash scripts/remote-control.sh logs

remote-doctor:
	@bash scripts/remote-control.sh doctor

network-static:
	@python3 -m unittest discover -s tests -p 'test_*.py' -v
	@bash scripts/test-security-static.sh

login:
	$(COMPOSE) exec agent codex login --device-auth

codex:
	$(COMPOSE) exec agent codex

shell:
	$(COMPOSE) exec agent bash

test:
	@bash scripts/run-project-command.sh test

race:
	@bash scripts/run-project-command.sh race

integration:
	@bash scripts/run-project-command.sh integration

deps-lint:
	@bash scripts/run-project-command.sh lint

logs: deps-generate
	$(COMPOSE) logs -f

logs-example: deps-generate
	$(COMPOSE_EXAMPLE) logs -f

ps: deps-generate
	$(COMPOSE_WEB) ps

ps-example: deps-generate
	$(COMPOSE_EXAMPLE) ps

reset-state:
	@bash scripts/cleanup.sh --volumes
