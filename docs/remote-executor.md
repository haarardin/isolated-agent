# Experimental outbound OpenAI Agents API executor

This feature is a first stage toward remote work with our existing rootless
Podman development environment. It is NOT a native ChatGPT Android/web Remote
host registration, and this PR does NOT implement native ChatGPT UI control.
The OpenAI Agents API is a separate application-managed API. API model usage
is charged separately from ChatGPT subscription Codex usage.

Official reference:
https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted

## Architecture

    Host-only control utility (Go, using OPENAI_API_KEY)
       |
       +----HTTPS---> OpenAI Agents API managed Codex harness
                                    |
                                    | outbound executor relay
                                    |
       Podman isolated-agent <------+
       (codex exec-server, restricted CODEX_API_KEY)
       /workspace, optional Serena MCP

No incoming ports, Docker socket, Podman socket, or privileged containers.
The existing Codex CLI and Serena workflow remains unchanged.

## Credentials

Two DIFFERENT keys are required. Create them on the OpenAI Platform within
the SAME org, project and service account/user:

1. Application OPENAI_API_KEY: api.agents.read, api.agents.write and
   api.responses.write. Keep only on the trusted host. Do NOT put in the
   repository .env, a container, a Containerfile, or shell logs.
2. Restricted environment key: all other permissions None. Give this key
   only to codex exec-server as CODEX_API_KEY.

For a local proof of concept, create the ignored host-only file:

    mkdir -p .secrets
    umask 077
    printf 'CODEX_API_KEY=%s\n' "$OPENAI_EXECUTOR_API_KEY" > .secrets/remote-executor.env
    chmod 600 .secrets/remote-executor.env
    unset OPENAI_EXECUTOR_API_KEY

Do not share keys or print them. Agent-generated commands in the same
container security domain may inspect the executor's process environment.
A separate agent container/worktree per API session is a future hardening task.

## Getting started (host terminal)

Start the existing sandbox from PR #1, and run:

    make doctor
    make test-remote

Before using a live session, test that the installed Codex CLI supports
the currently alpha-featured command:

    bash scripts/compose.sh exec agent codex exec-server --help

The official guide currently installs @openai/codex@alpha. The existing
base image deliberately stays on its verified version; this PR does not
silently upgrade or replace it. If the command is missing, the remote
executor fails safely and requires a compatible official Codex image.

In a trusted host terminal, export the application key:

    export OPENAI_API_KEY='YOUR_APP_KEY'
    make remote-session-create

This returns JSON containing a session id, environment id, and remote_url.
Store these three fields: reconnect to the SAME session after interruptions.
The creation command is a real API operation (and may incur charges).

In a second host terminal, use the EXACT remote_url and environment.id from
the session response:

    make remote-exec REMOTE_URL='https://api.openai.com/v1/agents/api' \
      ENVIRONMENT_ID='YOUR_ENVIRONMENT_ID'

The URL shown is an EXAMPLE ONLY. Never invent the environment URL.
The wrapper allows only officially documented TLS hosts, validates the
environment id, checks local file permissions, locates a running project
agent by Compose labels and injects the restricted key into ONLY the exec
process with podman exec --env-file. The application API key never enters
the sandbox.

After receiving a connected event, monitor and send input from separate
host terminals:

    make remote-session-watch SESSION_ID='YOUR_SESSION_ID'
    make remote-session-status SESSION_ID='YOUR_SESSION_ID'
    make remote-session-send SESSION_ID='YOUR_SESSION_ID' \
      TASK='Inspect the Go module in /workspace without editing files' \
      IDEMPOTENCY_KEY='inspect-001'

Reuse the SAME idempotency key if retrying the SAME message after a network
failure; use a NEW key for each different logical message. HTTP 202 means
input accepted, not completed. Check session turn completion/failure events.
Streams do not replay all missed events; retrieve session state afterward.

## Constraints / security

- Each self-hosted session has its OWN environment ID/executor.
- Avoid simultaneously running CLI and API agent with write access to the
  same /workspace: use separate worktrees/containers for production.
- The executor is outbound-only and needs HTTPS api.openai.com and
  WebSocket codex-cloud-environments.chatgpt.com.
- Container recreation stops the executor; rerun the connection with the
  original environment id and remote_url.
- Existing rootless, read-only Podman isolation applies unchanged.
- No long-running public listener or inbound tunnel is part of this PR.
- The container can only access the existing mounts, including Codex state;
  a restricted API key is not a substitute for filesystem isolation.
- There is NO native web/mobile interface in this release. For that,
  OpenAI must support Linux as a native Remote host, or we must build a
  separately authenticated application (for example, ChatKit + Agents API).

## Acceptance criteria

1. make test-remote passes offline (unit, race and static checks).
2. Existing make doctor, make test and make race remain green.
3. The installed CLI has codex exec-server.
4. API session creation returns an environment id and remote URL.
5. Executor connects using only restricted key and outbound WebSocket.
6. Read-only Go inspection task returns a completed turn via Agents API.
7. Neither host keys nor project files escape the stated isolation policy.
8. Do NOT mark native Android/web UI requirement complete based only on 1-7.

API references:
https://developers.openai.com/api/docs/guides/agents-api/sessions
https://developers.openai.com/api/docs/guides/agents-api/environments/security
