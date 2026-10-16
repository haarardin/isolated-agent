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
SERENA_STATE_VOLUME ?= ./volumes/serena
CODEX_STATE_MOUNT_TYPE := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind codex --storage "$(CODEX_STATE_VOLUME)" --field mount-type)
CODEX_STATE_MOUNT_SOURCE := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind codex --storage "$(CODEX_STATE_VOLUME)" --field mount-source)
CODEX_NAMED_VOLUME := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind codex --storage "$(CODEX_STATE_VOLUME)" --field named-volume)
SERENA_STATE_MOUNT_TYPE := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind serena --storage "$(SERENA_STATE_VOLUME)" --field mount-type)
SERENA_STATE_MOUNT_SOURCE := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind serena --storage "$(SERENA_STATE_VOLUME)" --field mount-source)
SERENA_NAMED_VOLUME := $(shell python3 scripts/project-state.py --project-dir "$(PROJECT_DIR)" --compose-project "$(COMPOSE_PROJECT_NAME)" --kind serena --storage "$(SERENA_STATE_VOLUME)" --field named-volume)
# Explicit, one-time opt-in only for a pre-existing, unbound volume.
CODEX_BIND_EXISTING_STATE ?= false
SERENA_BIND_EXISTING_STATE ?= false
export PROJECT_DIR CODEX_PROJECT_KEY CODEX_STATE_VOLUME SERENA_STATE_VOLUME
export CODEX_STATE_MOUNT_TYPE CODEX_STATE_MOUNT_SOURCE CODEX_NAMED_VOLUME
export SERENA_STATE_MOUNT_TYPE SERENA_STATE_MOUNT_SOURCE SERENA_NAMED_VOLUME
export CODEX_BIND_EXISTING_STATE SERENA_BIND_EXISTING_STATE
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
COMPOSE_SERENA ?= $(COMPOSE) -f compose.yaml -f compose.web.yaml -f .generated/compose.tools.yaml -f compose.serena.yaml
COMPOSE_SERENA_EXAMPLE ?= $(COMPOSE) -f compose.yaml -f compose.web.yaml -f compose.example-services.yaml -f .generated/compose.tools.yaml -f compose.serena.yaml
COMPOSE_OFFLINE_EXAMPLE ?= $(COMPOSE) -f compose.yaml -f compose.example-services.yaml -f .generated/compose.tools.yaml
COMPOSE_OFFLINE_SERENA ?= $(COMPOSE) -f compose.yaml -f .generated/compose.tools.yaml -f compose.serena.yaml

BASE_IMAGE ?= localhost/isolated-agent-base:dev
CODEX_IMAGE ?= localhost/isolated-agent-codex:dev
DEPENDENCIES_IMAGE ?= localhost/isolated-agent-dependencies:dev
PROJECT_IMAGE ?= localhost/isolated-agent-project:dev
SERENA_IMAGE ?= localhost/isolated-agent-serena:dev
SERENA_VERSION ?= 1.7.0
SERENA_GOPLS_VERSION ?= v0.20.0

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

.PHONY: prepare-state memory-info network-info network-ensure remote-start remote-pair remote-status remote-stop remote-logs remote-doctor network-check network-static prepare-web migrate-network offline offline-example offline-serena preflight doctor build build-base build-codex build-project ensure-images ensure-base-image ensure-codex-image ensure-project-image ensure-serena-image test-image-reuse-static test-project-context-static up up-example down down-example stop-agent remove-agent recreate-agent clean reset-example-db login codex shell test race integration logs logs-example ps ps-example reset-state build-serena up-serena up-serena-example codex-serena ps-serena ps-serena-example serena-doctor test-serena-static down-serena down-serena-example

help:
	@printf '%s\n' \
	  'make preflight      Check host requirements' \
	  'make doctor         Check the running agent toolchain/runtime' \
	  'make build          Force-build base, Codex and project image layers' \
	  'make build-serena   Force-build optional Serena + gopls layer' \
	  'make ensure-images  Reuse existing images; build only missing layers' \
	  'make test-image-reuse-static Validate image reuse logic without Podman' \
	  'make test-project-context-static Validate /workspace project context rules' \
	  'make up-serena      Switch agent to Serena image' \
	  'make up-serena-example Recreate agent; keep example services' \
	  'make codex-serena   Open Codex with Serena available' \
	  'make serena-doctor  Verify Serena, gopls and MCP registration' \
	  'make test-serena-static Check optional integration without Podman' \
	  'make up             Start agent with filtered Squid egress' \
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
	@printf 'Serena (%s):       %s -> /root/.serena\n' "$(SERENA_STATE_MOUNT_TYPE)" "$(SERENA_STATE_MOUNT_SOURCE)"
	@printf '%s\n' 'Serena project memories remain in PROJECT_DIR/.serena/memories/'

preflight:
	@bash scripts/preflight.sh
	@python3 scripts/network-preflight.py --subnet "$(AGENT_SUBNET)" --project "$(COMPOSE_PROJECT_NAME)" --network-name "$(AGENT_NETWORK_NAME)" --state .state/network.json

network-info:
	@python3 scripts/network-preflight.py --subnet "$(AGENT_SUBNET)" --project "$(COMPOSE_PROJECT_NAME)" --network-name "$(AGENT_NETWORK_NAME)" --state .state/network.json

network-ensure: preflight
	@python3 scripts/network-preflight.py --ensure --subnet "$(AGENT_SUBNET)" --project "$(COMPOSE_PROJECT_NAME)" --network-name "$(AGENT_NETWORK_NAME)" --state .state/network.json

prepare-state:
	@python3 scripts/prepare-state.py --codex-type "$(CODEX_STATE_MOUNT_TYPE)" --codex-source "$(CODEX_STATE_MOUNT_SOURCE)" --serena-type "$(SERENA_STATE_MOUNT_TYPE)" --serena-source "$(SERENA_STATE_MOUNT_SOURCE)"

prepare-web: network-ensure prepare-state deps-generate
	@bash scripts/prepare-web.sh

doctor:
	@bash scripts/doctor.sh

build: build-base build-codex build-project

# Fast bootstrap for additional repository clones on the same rootless-Podman
# host. Podman image storage is shared by tag for the current host user, so
# reuse an existing image instead of invoking a redundant build.
#
# This intentionally checks only image existence. If project-specific build
# image-level inputs changed (for example CODEX_AGENTS_FILE,
# PROJECT_APT_PACKAGES or Codex system defaults), use
# make build-project && make build-serena to refresh them. Project-specific
# context should normally live under PROJECT_DIR (/workspace) instead.
ensure-images: ensure-serena-image

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

ensure-serena-image: ensure-project-image
	@if $(PODMAN) image exists "$(SERENA_IMAGE)"; then \
		printf 'Reusing existing image: %s\n' "$(SERENA_IMAGE)"; \
	else \
		printf 'Image missing, building: %s\n' "$(SERENA_IMAGE)"; \
		$(MAKE) build-serena; \
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

build-project:
	$(PODMAN) build \
		-f images/project/Containerfile \
		--build-arg CODEX_IMAGE="$(CODEX_IMAGE)" \
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

# The outer project image must exist before the optional layer is built.
build-serena:
	$(PODMAN) build \
		-f images/serena/Containerfile \
		--build-arg PROJECT_IMAGE="$(PROJECT_IMAGE)" \
		--build-arg SERENA_VERSION="$(SERENA_VERSION)" \
		--build-arg GOPLS_VERSION="$(SERENA_GOPLS_VERSION)" \
		-t $(SERENA_IMAGE) \
		.

# Swapping image requires removing the previous agent container;
# persistent codex-state and agent-cache volumes are deliberately untouched.
# Do not invoke this while a Codex session is actively running.
up-serena: prepare-web
	$(COMPOSE_WEB) up -d squid
	@bash scripts/remove-service.sh agent
	$(COMPOSE_SERENA) up -d agent

# Recreate only the agent: podman-compose up -d (without a service)
# attempts to re-create existing PostgreSQL/Redis containers on some versions.
# Bootstrap the optional services once with make up-example.
up-serena-example: prepare-web
	$(COMPOSE_WEB) up -d squid
	@bash scripts/remove-service.sh agent
	$(COMPOSE_SERENA_EXAMPLE) up -d agent

codex-serena:
	$(COMPOSE_SERENA) exec agent codex

serena-doctor:
	@bash scripts/serena-doctor.sh

test-serena-static:
	@bash scripts/test-serena-static.sh

ps-serena:
	$(COMPOSE_SERENA) ps

ps-serena-example:
	$(COMPOSE_SERENA_EXAMPLE) ps

down-serena:
	$(COMPOSE_SERENA) down

down-serena-example:
	$(COMPOSE_SERENA_EXAMPLE) down

up: prepare-web
	@bash scripts/check-agent-state.sh
	$(COMPOSE_WEB) up -d

up-example: prepare-web
	@bash scripts/check-agent-state.sh
	$(COMPOSE_EXAMPLE) up -d

offline: network-ensure prepare-state deps-generate
	@bash scripts/check-agent-state.sh
	@bash scripts/remove-service.sh squid
	$(COMPOSE) up -d agent

offline-example: network-ensure prepare-state deps-generate
	@bash scripts/check-agent-state.sh
	@bash scripts/remove-service.sh squid
	$(COMPOSE_OFFLINE_EXAMPLE) up -d

offline-serena: network-ensure prepare-state deps-generate
	@bash scripts/remove-service.sh squid
	@bash scripts/remove-service.sh agent
	$(COMPOSE_OFFLINE_SERENA) up -d agent

down:
	$(COMPOSE_WEB) down

down-example:
	$(COMPOSE_EXAMPLE) down

migrate-network:
	@test "$(CONFIRM)" = "YES" || { echo "Set CONFIRM=YES; stop active Codex sessions first"; exit 1; }
	@bash scripts/migrate-network.sh
	@$(MAKE) up

stop-agent:
	$(COMPOSE_EXAMPLE) stop agent

remove-agent:
	@bash scripts/remove-service.sh agent

recreate-agent: prepare-web
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
	$(COMPOSE) exec agent bash -c 'if [ -f Makefile ] && grep -qE "^test:" Makefile; then make test; else go test ./...; fi'

race:
	$(COMPOSE) exec agent go test -race ./...

integration:
	$(COMPOSE) exec agent bash -c 'if [ -f Makefile ] && grep -qE "^integration:" Makefile; then make integration; else go test -tags=integration ./...; fi'

logs:
	$(COMPOSE) logs -f

logs-example:
	$(COMPOSE_EXAMPLE) logs -f

ps:
	$(COMPOSE_WEB) ps

ps-example:
	$(COMPOSE_EXAMPLE) ps

reset-state:
	@bash scripts/cleanup.sh --volumes
