# Agentic Bridge development workspace

Four independent Git repositories live below /workspace:
- agentic-bridge-architecture: authoritative ADRs, contracts, roadmap.
- agentic-bridge-cli: Go client and agent adapters.
- agentic-bridge-server: Go server, Postgres and migrations.
- agentic-bridge-ui: React/TypeScript/Vite frontend.

Read the target repository's AGENTS.md and architecture/PROJECT_CONTEXT.md
before changes. Do not create a root .git directory, go.mod or package.json:
run toolchains from each repository. Coordinate contract changes with the
architecture repository. Never put credentials or tokens in Git. Keep
Podman orchestration on the host: never mount runtime sockets into Codex.
The internal mock at http://mock-agent:8090 is a test-only HTTP fixture,
NOT yet connected to the production CLI. Published dev ports: 5173/8080.
No new PRs unless the operator explicitly requests them.
