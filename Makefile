ifneq (,$(wildcard ./.env))
include .env
export
endif

PODMAN ?= podman
COMPOSE ?= bash scripts/compose.sh
COMPOSE_EXAMPLE ?= $(COMPOSE) -f compose.yaml -f compose.example-services.yaml
COMPOSE_SERENA ?= $(COMPOSE) -f compose.yaml -f compose.serena.yaml
COMPOSE_SERENA_EXAMPLE ?= $(COMPOSE) -f compose.yaml -f compose.example-services.yaml -f compose.serena.yaml

BASE_IMAGE ?= localhost/isolated-agent-base:dev
CODEX_IMAGE ?= localhost/isolated-agent-codex:dev
PROJECT_IMAGE ?= localhost/isolated-agent-project:dev
SERENA_IMAGE ?= localhost/isolated-agent-serena:dev
SERENA_VERSION ?= 1.7.0
SERENA_GOPLS_VERSION ?= v0.20.0

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

.PHONY: help preflight doctor build build-base build-codex build-project up up-example down down-example stop-agent remove-agent recreate-agent clean reset-example-db login codex shell test race integration logs logs-example ps ps-example reset-state remote-session-create remote-session-send remote-session-status remote-session-watch remote-exec test-remote build-serena up-serena up-serena-example codex-serena ps-serena ps-serena-example serena-doctor test-serena-static down-serena down-serena-example

help:
	@printf '%s\n' \
	  'make preflight      Check host requirements' \
	  'make doctor         Check the running agent toolchain/runtime' \
	  'make build          Build all image layers' \
	  'make remote-session-create Create Agents API session (host key)' \
	  'make remote-exec    Connect restricted executor to Agents API' \
	  'make test-remote    Offline remote API unit/race/static tests' \
	  'make build-serena   Build optional Serena + gopls layer' \
	  'make up-serena      Switch agent to Serena image' \
	  'make up-serena-example Recreate agent; keep example services' \
	  'make codex-serena   Open Codex with Serena available' \
	  'make serena-doctor  Verify Serena, gopls and MCP registration' \
	  'make test-serena-static Check optional integration without Podman' \
	  'make up             Start the isolated agent' \
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
up-serena:
	@bash scripts/remove-service.sh agent
	$(COMPOSE_SERENA) up -d agent

# Recreate only the agent: podman-compose up -d (without a service)
# attempts to re-create existing PostgreSQL/Redis containers on some versions.
# Bootstrap the optional services once with make up-example.
up-serena-example:
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

up:
	$(COMPOSE) up -d agent

up-example:
	$(COMPOSE_EXAMPLE) up -d

down:
	$(COMPOSE) down

down-example:
	$(COMPOSE_EXAMPLE) down

stop-agent:
	$(COMPOSE_EXAMPLE) stop agent

remove-agent:
	@bash scripts/remove-service.sh agent

recreate-agent:
	@bash scripts/remove-service.sh agent
	$(COMPOSE_EXAMPLE) up -d agent

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

# Agents API control key stays on the host. These commands do not use Codex login.
# For the hosted API session's environment connection, use make remote-exec.
REMOTE_URL ?=
ENVIRONMENT_ID ?=
SESSION_ID ?=
TASK ?=
IDEMPOTENCY_KEY ?=

remote-session-create:
	cd tools/remote-session && go run . create

remote-session-send:
	cd tools/remote-session && go run . send --session "$(SESSION_ID)" --text "$(TASK)" --idempotency-key "$(IDEMPOTENCY_KEY)"

remote-session-status:
	cd tools/remote-session && go run . status --session "$(SESSION_ID)"

remote-session-watch:
	cd tools/remote-session && go run . watch --session "$(SESSION_ID)"

remote-exec:
	@bash scripts/remote-executor.sh "$(REMOTE_URL)" "$(ENVIRONMENT_ID)"

test-remote:
	@bash scripts/test-remote-static.sh
	@cd tools/remote-session && go test -race ./...
