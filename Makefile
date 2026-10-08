ifneq (,$(wildcard ./.env))
include .env
export
endif

PODMAN ?= podman
COMPOSE ?= bash scripts/compose.sh
COMPOSE_EXAMPLE ?= $(COMPOSE) -f compose.yaml -f compose.example-services.yaml

BASE_IMAGE ?= localhost/isolated-agent-base:dev
CODEX_IMAGE ?= localhost/isolated-agent-codex:dev
PROJECT_IMAGE ?= localhost/isolated-agent-project:dev

PROJECT_APT_PACKAGES ?=
CODEX_AGENTS_FILE ?= templates/AGENTS.project.md
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
CODEX_FEATURE_MEMORIES ?= false

.PHONY: help preflight doctor build build-base build-codex build-project up up-example down down-example clean reset-example-db login codex shell test race integration logs logs-example ps ps-example reset-state

help:
	@printf '%s\n' \
	  'make preflight      Check host requirements' \
	  'make doctor         Check the running agent toolchain/runtime' \
	  'make build          Build all image layers' \
	  'make up             Start the isolated agent' \
	  'make up-example     Start agent + PostgreSQL + Redis' \
	  'make ps-example     Show agent + example services' \
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

preflight:
	@bash scripts/preflight.sh

doctor:
	@bash scripts/doctor.sh

build: build-base build-codex build-project

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

up:
	$(COMPOSE) up -d agent

up-example:
	$(COMPOSE_EXAMPLE) up -d

down:
	$(COMPOSE) down

down-example:
	$(COMPOSE_EXAMPLE) down

clean:
	@bash scripts/cleanup.sh

reset-example-db:
	@bash scripts/reset-example-db.sh

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
	$(COMPOSE) ps

ps-example:
	$(COMPOSE_EXAMPLE) ps

reset-state:
	@bash scripts/cleanup.sh --volumes
