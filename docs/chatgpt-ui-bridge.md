# Native ChatGPT Android and web: proposed MCP plugin

Our requested outcome is to start and steer Codex development from the
native ChatGPT Android/web interface, not only from a terminal.

## Current support and boundaries

Agents API self-hosted environments provide an official outbound WebSocket
executor. This does NOT automatically register a Linux Podman host in the
ChatGPT Remote host picker, which uses a separate native desktop integration.

ChatGPT Work can connect an authenticated custom MCP Plugin. Official
documentation allows public HTTPS or Secure MCP Tunnel for private servers.
Work runs on eligible ChatGPT web and mobile platforms.

References:
https://developers.openai.com/plugins/quickstart
https://developers.openai.com/plugins/build/mcp-server
https://developers.openai.com/plugins/deploy/connect-chatgpt
https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted

## Proposed control plane (subsequent PR)

    ChatGPT Android/web (Work + authenticated custom MCP Plugin)
                  |
                  v
       Go control service on a trusted VPS
       user auth, session authorization, task quotas
                  |
                  v
        OpenAI Agents API (application API key kept ONLY here)
                  |
         outbound authenticated WebSocket
                  |
                  v
       rootless Podman isolated-agent + Serena
       no incoming ports, no host socket, /workspace

The control plane must not accept arbitrary shell commands from a plugin
caller. It creates owner-scoped Agents API sessions with a fixed workspace.

Future MCP tools: list_workspaces, start_coding_task, get_task_status,
get_task_output, steer_task, cancel_task. Mutating operations require
explicit authorization and approval policies.

## Prerequisites and safeguards

A trusted controller endpoint, identity/auth scheme (OAuth 2.1 or supported
managed tunnel identity), secure key storage, rate limits, audit logging and
per-user session ownership are required. Do not expose unauthenticated task
submission to the public internet.

The ChatGPT Plugin is installed/configured by the user. Merely deploying
an MCP server does not activate it in anyone's account.

## Scope distinction

This PR only implements the outbound executor and host-side Go Agents API
client. There is no public web listener, custom MCP plugin, mobile app or
production OAuth service in it. The native Android/web story is incomplete.
The follow-up plugin can be stacked on this PR after the live API smoke test
and control-plane deployment choice.

## Native UI acceptance test (not completed)

1. Authorized Android or web Work chat starts task for an allowlisted repo.
2. User sees session progress and outputs with proper permissions.
3. Unknown users cannot view or create any sessions.
4. No host network listener, SSH credentials or Podman socket is exposed.
5. Codex CLI and Serena continue to work without the plugin.
