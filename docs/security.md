# Security considerations: Codex Remote Control

Rootless Podman remains the **primary** sandbox. The agent is container
root mapped to an unprivileged host user. Runtime image root filesystem
is read-only, Linux capabilities are all dropped, and `no-new-privileges`
is enabled. The agent only mounts PROJECT_DIR, codex-state and agent-cache;
Serena adds its own named volume. An image-baked symlink maps
`/root/Documents` to the existing `/workspace` host bind for projectless
Codex Remote Control sessions. No additional host directory is mounted.
No host root, socket, SSH keys, privileged mode, host network or inbound
public control port is exposed.

The existing Codex settings `approval_policy = "never"` and
`sandbox_mode = "danger-full-access"` are deliberately unchanged.
**Remote Control grants the paired device authority to request filesystem
changes and command execution inside the agent**. Do not pair a device
you do not trust; keep only a disposable/appropriate source tree
in PROJECT_DIR. Remote access to the same account is a powerful
capability despite rootless Podman, and can delete workspace files.

New Android Remote threads without an explicitly selected project can
use `/root/Documents/Codex`. The image maps `/root/Documents` to
`/workspace` with a fixed symlink (not a second host bind mount).
These generated folders are therefore accessible inside the same
approved host `PROJECT_DIR`. Because remote users already have code
execution authority within the writable workspace, use a disposable
directory for untrusted experiments. The root remains read-only.

The stored `/root/.codex` named volume contains sensitive auth tokens,
session history, daemon settings and pairing/enrollment state. It
survives normal `down`/recreation. Never run `make reset-state`
unless its destruction is intended. Protect rootless host storage,
backups, environment variables and Git working directories.

`make remote-pair` prints a short-lived credential ONLY to the invoking
terminal. Do not redirect that output to persistent logs or CI.
`remote-start`/`remote-stop` suppress raw Codex output; recorded
`.state/remote-events.log` contains only lifecycle events, protected
by mode 0600 and excluded from Git. `remote-logs` intentionally does not
tail Codex's real logs, which may include code, file paths and tokens.

Network: see [network-isolation.md](network-isolation.md). The only
outbound gateway is trusted Squid with dst ACLs; CIDR blocking via
an application-level proxy is not a formal firewall proof.
Validate host/VPN/IPv6/DNS and user-defined BLOCK_CIDRS on Debian.

Remote session state and ordinary ChatGPT chat history are not
necessarily synchronized. Mobile pairing availability is version-
and workspace-dependent; see [remote-control.md](remote-control.md).

Maintain separate Compose project names and persistent volumes.
Prefer independent networks; share a named bridge only between trusted
projects with explicit AGENT_NETWORK_NAME. Never bind other projects'
Codex auth volumes or PostgreSQL data directories into active containers.

## Shared internal networks

A network selected by `AGENT_NETWORK_NAME` can be used by multiple
independent Compose projects. Their Codex credentials, named volumes and
container names remain separate because they use distinct
`COMPOSE_PROJECT_NAME` values. However, all containers on the shared
bridge may contact one another's network services: this is **not**
tenant isolation, and Squid's CIDR restrictions are not a firewall
between these projects. Trust every project joining the network.
Use project-qualified DNS aliases for proxy and database endpoints.

## Codex native memory and state volumes

The full CODEX_HOME, including native memory SQLite files, is bound to
a project-specific named volume selected by CODEX_STATE_VOLUME. By default
the volume name is derived from the Compose identity plus canonical
host PROJECT_DIR. An in-volume identity marker refuses cross-project
reuse even if a caller explicitly chooses the same volume name.
A populated legacy volume without the marker requires deliberate
one-time CODEX_BIND_EXISTING_STATE=true.

SERENA_STATE_VOLUME persists global Serena data at /root/.serena;
project-specific Serena memories stay at PROJECT_DIR/.serena/memories/.
Both types of named volume survive container deletion but not volume
deletion. Never share one CODEX_HOME among concurrently running agents
(SQLite and credential isolation). Backup only after stopping Codex.
