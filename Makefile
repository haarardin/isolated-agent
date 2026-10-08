PODMAN ?= podman
COMPOSE ?= $(PODMAN) compose

BASE_IMAGE ?= localhost/isolated-agent-base:dev
CODEX_IMAGE ?= localhost/isolated-agent-codex:dev
PROJECT_IMAGE ?= localhost/isolated-agent-project:dev

.PHONY: help preflight build build-base build-codex build-project up up-example down login codex shell test race integration logs ps reset-state

help:
	@printf '%s\n' \
	  'make preflight      Check host requirements' \
	  'make build          Build all image layers' \
	  'make up             Start the isolated agent' \
	  'make up-example     Start agent + PostgreSQL + Redis' \
	  'make login          Authenticate Codex using device flow' \
	  'make codex          Open interactive Codex CLI' \
	  'make shell          Open a shell inside the agent' \
	  'make test           Run the project unit-test command' \
	  'make race           Run Go race tests' \
	  'make integration    Run project integration tests' \
	  'make logs           Follow compose logs' \
	  'make down           Stop the environment' \
	  'make reset-state    Delete containers and named volumes'

preflight:
	@./scripts/preflight.sh

build: build-base build-codex build-project

build-base:
	$(PODMAN) build \
		-f images/base/Containerfile \
		-t $(BASE_IMAGE) \
		.

build-codex:
	$(PODMAN) build \
		-f images/codex/Containerfile \
		--build-arg BASE_IMAGE=$(BASE_IMAGE) \
		-t $(CODEX_IMAGE) \
		.

build-project:
	$(PODMAN) build \
		-f images/project/Containerfile \
		--build-arg CODEX_IMAGE=$(CODEX_IMAGE) \
		-t $(PROJECT_IMAGE) \
		.

up:
	$(COMPOSE) up -d agent

up-example:
	$(COMPOSE) -f compose.yaml -f compose.example-services.yaml up -d

down:
	$(COMPOSE) down

login:
	$(COMPOSE) exec agent codex login --device-auth

codex:
	$(COMPOSE) exec agent codex

shell:
	$(COMPOSE) exec agent bash

test:
	$(COMPOSE) exec agent bash -lc 'if [ -f Makefile ] && grep -qE "^test:" Makefile; then make test; else go test ./...; fi'

race:
	$(COMPOSE) exec agent go test -race ./...

integration:
	$(COMPOSE) exec agent bash -lc 'if [ -f Makefile ] && grep -qE "^integration:" Makefile; then make integration; else go test -tags=integration ./...; fi'

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

reset-state:
	$(COMPOSE) down -v --remove-orphans
