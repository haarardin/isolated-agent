# Project agent instructions

Adapt this file and place it at the root of the target project as AGENTS.md.

## Project

Describe the application and important architecture boundaries here.

## Development environment

The project runs inside an isolated-agent development container.

Writable project directory:

```text
/workspace
```

Do not assume access to host files outside this directory.

## Services

Document Compose service endpoints here.

Example:

```text
PostgreSQL: postgres:5432
Redis:      redis:6379
```

Use service DNS names unless this project explicitly uses a shared Pod network namespace.

## Required checks

Before declaring a code-changing task complete, run all checks that apply:

```bash
go test ./...
go test -race ./...
make integration
```

If a check fails:

1. inspect the failure;
2. inspect relevant service/application logs available inside the environment;
3. fix the code or test environment;
4. rerun the failed check;
5. rerun the full required test set.

Do not report success while required tests are failing.

## Project-specific constraints

Add code style, generated-file rules, migration rules, protocol requirements, and directories that must not be modified here.
