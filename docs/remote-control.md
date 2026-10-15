# Codex Remote Control (experimental headless mode)

This is an opt-in mode for the **official Codex CLI** already installed in
this repository. No desktop GUI, Linux `.deb`, host SSH agent, systemd in
the container or incoming TCP listener is required.

Source of truth: [Codex developer commands](https://learn.chatgpt.com/docs/developer-commands)
and [managed app-server daemon](https://github.com/openai/codex/blob/main/codex-rs/app-server-daemon/README.md).
Both CLI features and mobile pairing availability may change with releases.

## Debian 13 setup and migration

The old repository used a non-internal network. **Do not keep the old
network** when testing restricted egress.

```bash
git switch feature/remote-control-network-isolation
cp -n .env.example .env
# Edit .env: PROJECT_DIR, distinct COMPOSE_PROJECT_NAME, unique AGENT_SUBNET.
# Preserve existing .env / named volumes / credentials.
make network-static
make preflight       # intentionally rejects an old unrestricted network
# Existing install ONLY, after saving active work:
CONFIRM=YES make migrate-network
```

The migration stops Compose containers but **never uses down -v**.
It retains codex-state, agent-cache, Serena and Postgres volumes. If you
are using Serena or example services, restart the corresponding combination
after migration (`make up-serena` or `make up-example`). Do not delete
networks still used by other projects. Back up valuable state first.

We changed the Codex image and entrypoint so the managed standalone
binary is seeded into the existing persistent CODEX_HOME volume when
absent; this does not overwrite tokens or sessions. Rebuild the changed
image layers, even if make ensure-images would otherwise reuse them:

```bash
make build-codex
make build-project
# Optional when using Serena:
make build-serena
make up
make login             # one-time ChatGPT device authorization
make doctor
make network-check
```

## Headless remote commands

```bash
make remote-start      # managed app-server daemon, detached inside agent
make remote-status     # checks daemon status via CLI JSON (no raw JSON logged)
make remote-doctor     # CLI, writable CODEX_HOME, proxy HTTPS, network
make remote-pair       # print code DIRECTLY in the operator terminal
make remote-stop
make remote-logs       # lifecycle events only; deliberately not raw Codex logs
```

`make codex` continues to launch an ordinary interactive TUI. Both
use the same CODEX_HOME. Remote Control manages a detached app-server
with PID, lock, Unix socket and settings stored under
`/root/.codex/app-server-daemon`. `make remote-start` checks that it
is **still running after `podman exec` exits**, rather than treating
successful CLI invocation as proof. Multiple starts should be idempotent.

A container recreation destroys its processes, but not CODEX_HOME.
After `make up` / `make up-serena` / a host reboot restart with
`make remote-start`. The current implementation uses the official
managed daemon; there is no extra supervisor or PID1 patch. It does not
automatically restart after Podman container recreation. For unattended
VPS operation, arrange a **host-side user service** that runs make up
and make remote-start after Podman is available; do not install systemd
inside the container. If the daemon unexpectedly exits, use
`make remote-status` and re-run `make remote-start`.

**Secrets:** pairing codes expire quickly and are sensitive. The pair
command deliberately prints the code to the operator's terminal and
does not save it to a file. Never paste into CI, chat logs, GitHub,
or screen shares. Start/stop suppress raw CLI output to avoid leaking
tokens, codes or filenames. The safe `remote-logs` command only shows
timestamped lifecycle events, **not** raw Codex log output.

## Manual Android E2E checklist (not automated)

1. Update the ChatGPT Android app and sign in to the **same account
   and workspace** as the `make login` authorization.
2. Verify `make remote-status`, then `make remote-doctor`.
3. In a private host terminal run `make remote-pair`; note the
   short-lived code privately and the expiration shown by Codex.
4. In Android open **Codex** (or **Remote** if that is the available
   UI). Look for a host-pairing flow that accepts a manual code.
   **If only QR pairing from a Mac/Windows Desktop is offered, stop
   here:** do not pretend that CLI pairing is exposed in that app build.
5. If a manual-code entry is supported, enter the code, complete any
   required verification, select the connected host/project.
6. Send a harmless task: "Create /workspace/remote-e2e.txt with
   contents remote-ok; then read it back and report its contents".
7. On Debian verify file appears under PROJECT_DIR, and verify in
   Android that you can read results and continue the same session.
8. Disconnect/reconnect Android, restart the managed daemon with
   `make remote-stop && make remote-start`, then re-check pairing.
9. Recreate the container only after saving work; repeat
   `make remote-start`, verify CODEX_HOME session/auth continuity
   and whether Android rediscovers the host. Re-pair if required.

**Important product limitation:** the mainstream
[Remote connections guide](https://learn.chatgpt.com/docs/remote-connections)
describes desktop-initiated QR pairing on macOS/Windows; it does not
promise a Linux CLI manual pairing UI in every Android build. The
[Codex CLI documentation](https://learn.chatgpt.com/docs/developer-commands)
documents `remote-control pair`, which is experimental. A valid code
alone does not prove the Android controller supports it.

Do not assume ordinary ChatGPT conversations, Codex Web, TUI history
and Remote Control sessions automatically share identical state.

## Troubleshooting

- `remote-control` subcommand missing: check `codex --version` and
  the installed managed CLI; `make build-codex && make build-project`
  after upgrading images.
- Managed binary absent: `make remote-start` will fail; check
  `/root/.codex/packages/standalone/current/codex` through a
  private `make shell`, and review installer compatibility.
- Start succeeded but daemon absent: the local check fails; inspect
  daemon implementation/version on that CLI. Do **not** publish a
  WebSocket port as a workaround.
- Pair says enrollment incomplete: check `make remote-doctor`,
  proxy DNS and OpenAI endpoint reachability; network restrictions
  must not be disabled merely to satisfy enrollment.
- Offline mode does **not** support Remote Control or online login.
- Debugging the official app-server sometimes requires local raw logs.
  Treat them as sensitive and do not paste them into public issues.
- WebSocket upgrades over HTTPS CONNECT depend on both Codex client and
  Squid behavior; this is a mandatory Debian runtime test.
