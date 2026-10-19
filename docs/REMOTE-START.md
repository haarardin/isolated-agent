# Start Codex Remote Control on Debian (rootless Podman)

This is the **start-to-finish operator runbook** for using the existing
`isolated-agent` as a headless, remotely accessible Codex worker from
ChatGPT/Codex on Android. All commands below run **on the Debian host,
as your normal user, in the `isolated-agent` repository directory**.
Do not use `sudo`. No Webtop GUI, public inbound port or Podman socket is
needed.

**What Remote Control does:** the Android app communicates with the
official managed Codex app-server over the remote-control service. The
container needs **filtered outbound HTTPS** through Squid, so use
`make up`, **not** `make offline`. Manual-code pairing is an
experimental CLI feature; the Android UI varies by app version. On the
tested Android setup, the host was visible and a remote turn reached
the agent, but completing a turn still needs the writable-workspace
verification below.

## A. First installation (new Compose project)

1. **Use a checkout containing these Make targets and create local config.**
   On an existing checkout, stay on its intended release/PR branch;
   the former `feature/remote-control-network-isolation` branch is not
   the current project state.

   ```bash
   git clone https://github.com/haarardin/isolated-agent.git
   cd isolated-agent
   # For an unmerged PR, check out its feature branch before proceeding.
   cp -n .env.example .env
   ```

   For an upgrade, use `git pull --ff-only` on the selected branch.
   Do not replace an existing `.env` or legacy Podman named volume.

2. **Choose what the remote agent may edit.**

   ```bash
   mkdir -p "$HOME/projects/codex-remote-workspace"
   nano .env
   ```

   In `.env`, set (replace `/home/USER` with the actual absolute path):

   ```dotenv
   COMPOSE_PROJECT_NAME=isolated-agent-demo
   PROJECT_DIR=/home/USER/projects/codex-remote-workspace
   AGENT_SUBNET=auto
   # Optional, only when sharing a trusted network with another project:
   # AGENT_NETWORK_NAME=team-development
   BLOCK_CIDRS=
   ```

   `PROJECT_DIR` **must exist**. Native Codex memories are enabled by default
   in the newly built project image. Persistent Codex state is selected
   automatically by source project, or with CODEX_STATE_VOLUME in .env.
   See [state migration](codex-config.md#upgrading-an-existing-codex-volume)
   before upgrading an existing installation.

   `PROJECT_DIR` **must exist**. It is mounted read-write as
   `/workspace`. In the current project image, `/root/Documents`
   is an image-baked symlink to `/workspace`; projectless mobile tasks
   may create files under `PROJECT_DIR/Codex`. Choose a **disposable**
   directory or only the repository you intend to grant Codex access to.
   Keep the other `.env` settings from `.env.example`.

   The default `auto` mode allocates a free subnet per new network and
   safely reuses an existing matching named network. For multiple
   independent clones, choose distinct `COMPOSE_PROJECT_NAME`.
   Set the same `AGENT_NETWORK_NAME` only for trusted projects that
   must share a network. Distinct `COMPOSE_PROJECT_NAME` values
   prevent Compose service and named-volume collisions.
   To select a specific subnet, set `AGENT_SUBNET` to an unused
   IPv4 CIDR. `BLOCK_CIDRS` optionally denies additional
   host/VPN/private IP ranges through Squid.

   Persistent state is stored by default in
   `isolated-agent/volumes/codex/<project-key>` and
   `isolated-agent/volumes/serena/<project-key>`. The folders are
   created automatically at startup; no manual `mkdir` is needed.
   The `.env.example` defaults are `CODEX_STATE_VOLUME=./volumes/codex`
   and `SERENA_STATE_VOLUME=./volumes/serena`.

3. **Check dependencies, scripts and network topology.**

   ```bash
   make network-static
   make preflight           # plan: no changes to Podman networks
   make memory-info         # shows effective local memory storage directories
   make network-info        # show planned or reusable configured network
   ```

   Requirements: rootless Podman, explicit `podman-compose`,
   **Python 3.11+** on the host (the generator uses stdlib `tomllib`),
   GNU Make, Git and access to the official Codex CLI installer for
   the image build. The preflight must succeed before the next step.
   If it rejects an **existing same-project network because it is
   `internal: false`**, follow section **C**, below. Do **not**
   blindly migrate on every install or ignore a collision with
   another project's network.

4. **Build the agent image layers, start the online profile and check
   the network.**

   ```bash
   make build             # Base + Codex CLI + Dependencies + Project
   make up                # agent plus dual-homed filtered Squid
   make ps
   make doctor
   make network-check
   ```

   `make build` is the safe first-install option: `make ensure-images`
   only checks if existing tags are present and will not update an old
   image after a Dockerfile change. `make up` creates the agent on
   an `internal: true` Podman network; only Squid connects to the
   outbound network. No extra `make recreate-agent` is needed on a
   **brand-new** installation just built from the updated images.

5. **Sign in to Codex, start Remote Control and check readiness.**

   ```bash
   make login             # follow ChatGPT device authorization; first time
   make remote-start      # starts detached managed Codex daemon
   make remote-status
   make remote-doctor
   ```

   The login uses your ChatGPT account. Do not copy authentication
   files into the chat. Expect a running daemon and a writable
   `/root/Documents` check, plus an OpenAI HTTPS CONNECT check
   through Squid. `make remote-doctor` is also useful after upgrades.

6. **Pair Android and send a harmless first turn.**

   ```bash
   make remote-pair
   ```

   This prints a short-lived pairing code **only in your private
   terminal**. On Android, sign in to the **same ChatGPT account and
   workspace**, open **Codex / Remote**, find the option to pair or add
   the remote host and enter the code **if your app offers manual-code
   pairing**. Names and available pairing flows vary by release.
   Never post the code or full authentication/session logs.

   Select the connected remote host, open a new thread and send:

   > List the filenames in /workspace and tell me the current working directory. Do not modify files.

   Then try a small write:

   > Create /workspace/remote-e2e.txt containing remote-ok, read it back, and report the result.

   On the Debian host:

   ```bash
   cat /home/USER/projects/codex-remote-workspace/remote-e2e.txt
   ```

   Expected: `remote-ok`. The host/source path is the same
   `PROJECT_DIR` set in your `.env`, not a path in the agent repo.
   A visible device/host alone does **not** prove successful turn
   execution; verify a response **and** the host file.

## B. Upgrade an existing agent (images and persistent data already present)

If you need to preserve Codex authentication/history from an existing
installation, **first select or export the old named volume** as described in
[Codex volume migration](codex-config.md#upgrading-an-existing-codex-volume).
Do not silently switch to a fresh empty CODEX_STATE_VOLUME.

This is the shortest safe sequence for an existing instance from an older
PR #6 revision, especially one that fails with
`mkdir: cannot create directory '/root/Documents': Read-only file system`.

```bash
# From the existing isolated-agent checkout; finish/save active tasks first.
# Stay on the branch containing the current PR/release.
git pull --ff-only
make network-static
make preflight

make build-project        # adds /root/Documents -> /workspace to the image
make recreate-agent       # deploys image; does NOT delete named volumes
make network-check
make remote-start         # daemon was stopped by container recreation
make remote-status
make remote-doctor
```

`make recreate-agent` deliberately recreates **only agent**; Squid,
PostgreSQL/Redis services, networks and named volumes are not reset.
`make up` alone may leave an existing container on the old image.
If you need an updated Codex CLI as well, first run
`make build-codex && make build-project` before `make recreate-agent`.
If you were not logged in previously, run `make login` after recreation.
If Android was paired already, **test the existing connection first**;
only re-run `make remote-pair` if pairing is lost.

For **Serena-enabled** agents (only if you are actually using Serena):

```bash
make build-project
make build-serena
make up-serena
make network-check
make remote-start
make remote-doctor
```

Do **not** use ordinary `make recreate-agent` for this scenario: it
targets `PROJECT_IMAGE`, not the Serena-derived image. For a new Serena
environment first build the base and Codex layers (e.g. `make build`),
then `make build-serena && make up-serena`.

## C. Existing older network: migrate **only if preflight rejects it**

The previous agent network used `internal: false`. On an existing
project, if `make preflight` reports that this **same project's**
`isolated-dev` network is not internal:

```bash
# Finish/save active Codex tasks; back up valuable bind/named-volume state.
CONFIRM=YES make migrate-network
make preflight
make network-check
```

`migrate-network` runs Compose `down` **without `-v`**, then starts
the filtered web profile. It stops running sessions, but preserves the default Codex/Serena
host bind state as well as existing `agent-cache`, DB and legacy
named volumes. If you
were using optional services, restart the relevant profile afterward;
restart the managed daemon with `make remote-start`. Do not use this
command to fix an unrelated subnet collision with another project,
and do not remove someone else's attached network.

If `make preflight` reports `Project network planned` (fresh
installation) or `Project network reused`, **skip migration**.

## D. Regular use after an agent restart/recreation

```bash
make stop              # operator-requested shutdown of existing containers
make start             # resume the saved set; no Compose up or recreation
make remote-start      # daemon processes do not survive stop/start
make remote-status
```

For the **first start** or recovery with no `make stop` checkpoint,
use `make up` (not `make start`). After image or configuration changes,
rebuild/recreate the agent instead of resuming unchanged containers.
Codex sessions, authentication and memories default to the
`./volumes/codex/<project-key>` host bind directory, or an explicitly
selected legacy named volume. `make remote-start` does not run
automatically on host boot. To
stop remote management without deleting data:

```bash
make remote-stop
make remote-logs        # safe lifecycle events, no raw auth/pairing output
```

For a completely unattended service, arrange a **host-side user
service** to start Compose and then `make remote-start`; no
systemd-in-container or public TCP listener is required.

## E. Diagnosing failures without weakening isolation

| Symptom | What to do |
|---|---|
| `make preflight` reports an old non-internal network | Use section C *only if it is this Compose project's network* |
| `make network-check` returns `000` for 127.0.0.1 | Pull the updated PR script; Squid ACL tests must use `curl --noproxy '' -x "$HTTP_PROXY"` |
| `remote-start` cannot find a container | Run `make up` and `make ps` |
| `remote-start` refuses due to missing Squid | Run `make up`, not `make offline`; then `make network-check` |
| Remote daemon reports stopped | Run `make remote-start`, then `make remote-status` |
| `/root/Documents` read-only error on Android | Rebuild **project** image and `make recreate-agent` as in B; do **not** disable `read_only` |
| CLI lacks `remote-control` | Rebuild Codex and project images, recreate agent and verify `codex --version` |
| HTTPS/CONNECT fails in `make remote-doctor` | Verify `make network-check`, Squid ACL/DNS and egress; do not attach an outbound network directly to agent |
| Host visible on Android but remote turn fails | Check `make remote-doctor`; then inspect the writable workdir and try a **new** remote thread |
| Android has no manual pairing UI | CLI pairing is experimental and not promised for every Android build; check the app version/available pairing flow |

Inspect the Documents alias without exposing file contents:

```bash
make shell
readlink /root/Documents            # should print /workspace
test -w /root/Documents && test -w /workspace && echo OK
exit
```

Keep `read_only: true`, drop all capabilities, retain internal-only
agent networking, and use the Squid proxy for outbound HTTPS. Do not
attach the Podman/Docker socket or blanket-mount host `$HOME`.

**Persistent data:** the complete `/root/.codex` (auth, sessions,
memories and SQLite) defaults to a gitignored host bind directory,
`./volumes/codex/<project-key>`; an existing named volume can also
be selected explicitly. `agent-cache:/root/.cache` holds build caches;
`PROJECT_DIR` is the approved source directory. `make reset-state`
is destructive for named volumes and does not replace backups for
host bind state. Never use it to debug Remote Control.

For implementation details and security limitations see
[Remote Control reference](remote-control.md),
[network isolation and migration](network-isolation.md) and
[security](security.md).
