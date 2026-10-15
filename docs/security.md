# Security considerations: Codex Remote Control

Rootless Podman remains the **primary** sandbox. The agent is container
root mapped to an unprivileged host user. Runtime image root filesystem
is read-only, Linux capabilities are all dropped, and `no-new-privileges`
is enabled. The agent only mounts PROJECT_DIR, codex-state and agent-cache;
Serena adds its own named volume. For Codex Remote Control compatibility,
PROJECT_DIR is also mapped to /root/Documents as a **second alias of
the same host directory** already mounted at /workspace. It does not
grant access to any new host paths and does not make the container root
writable. A remote task targeting ~/Documents therefore writes to
the same approved project source tree. No host root, socket, SSH keys,
privileged mode, host network or inbound public control port is mounted.

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

Maintain separate Podman Compose project names/networks/subnets and
do not bind other projects' Codex auth volumes or Postgres data
directories across concurrent containers.
