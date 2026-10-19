# Agent network isolation (rootless Podman)

For the exact ordered commands to start the filtered online agent and
pair an Android device, see
[REMOTE-START.md](REMOTE-START.md). The network migration below is
**conditional**, not part of a fresh installation.

## Separate Compose and network identities

`COMPOSE_PROJECT_NAME` scopes a deployment's Compose containers and
named volumes; the default Codex/Serena host bind state is also keyed
by this identity and canonical `PROJECT_DIR`.
**`AGENT_NETWORK_NAME` separately names its Podman bridge.**
Leave the latter unset for the previous default
`<COMPOSE_PROJECT_NAME>_isolated-dev`.

Two trusted projects can set **the same network name**:

```dotenv
# Checkout A
COMPOSE_PROJECT_NAME=codex-api
AGENT_NETWORK_NAME=team-development
AGENT_SUBNET=auto

# Checkout B
COMPOSE_PROJECT_NAME=codex-sip
AGENT_NETWORK_NAME=team-development
AGENT_SUBNET=auto
```

Both connect to `team-development`, while the Compose containers and
named volumes remain independent. Each checkout's ignored
`.state/network.json` records that same network name and CIDR.

The startup sequence:

1. `make preflight` and `make network-info` inspect existing networks
   without changing them.
2. `make network-ensure` searches by **AGENT_NETWORK_NAME**.
3. If present, it validates internal-only IPv4 bridge settings, CIDR and
   applicable provenance labels; an explicitly named shared network
   may carry the other project's legacy owner label.
4. If absent, it selects a free `/24` from `10.203.0.0/16` with
   `AGENT_SUBNET=auto` (or validates an explicit unused CIDR), creates
   the network and stores its CIDR locally.
5. `make up` / `make offline` call `make network-ensure`; the internal
   network is declared `external: true`, so Compose `down` preserves it.

```bash
make network-info
make network-ensure
make up
make network-check
podman network inspect team-development
```

**Security consequence:** a shared network is a shared *trust zone*,
not isolation between projects. Member containers can contact listening
services belonging to other projects. Squid's denylist protects
outbound traffic via Squid, not cross-project bridge traffic.
Service-name DNS aliases such as `postgres`, `redis`, and `squid`
may be ambiguous on the shared network. Agent traffic uses a unique
`<COMPOSE_PROJECT_NAME>-egress` alias; example database clients use
`<COMPOSE_PROJECT_NAME>-postgres` and
`<COMPOSE_PROJECT_NAME>-redis`. Trust all network members.

### Switching an existing project to a shared network

After updating `.env` with the new AGENT_NETWORK_NAME:

```bash
make network-info
make network-ensure
make up
make recreate-agent    # apply changed network and proxy environment
make network-check
make remote-start      # restart managed daemon after agent recreation
```

Serena users should replace `make recreate-agent` with
`make up-serena`. Old external networks and named volumes are not
deleted when changing the name. `make migrate-network` is only for
migrating the former insecure project-named network, and is **not**
the way to switch to a shared network.

## Topology

```text
Codex agent (internal-only network, AGENT_SUBNET)
     |             |                 |
 /workspace     postgres          redis
     |
     +----> <project>-egress:3128 / Squid (internal + outbound)
                    |
                Internet
```

Only Squid is dual-homed. The host-provisioned network is `internal: true`
with the project's resolved `AGENT_SUBNET`; `compose.web.yaml` adds Squid
and outbound network. The internal network is prepared by a host script
and declared `external: true` in Compose, so the `internal` property
is checked in **Podman inspect**, not inferred from the external Compose stanza. The agent has one isolated network attachment
in both modes; `HTTP_PROXY` alone is NOT a security boundary.

```bash
make up              # filtered web, Squid on isolated + outbound
make offline         # remove Squid; launch enabled internal Agent Tools
make up-example      # filtered web + postgres/redis
make offline-example # offline with postgres/redis and enabled sidecars
make up-serena       # filtered web + Serena
make network-check   # runtime checks; does NOT prove total isolation
```

Squid uses `config/squid.conf` with ACL blocked_dst built from
`config/blocked-cidrs.txt` and extra comma-separated `BLOCK_CIDRS`.
No outbound ports are published. It blocks loopback, RFC1918, CGNAT,
link-local, metadata, special-use IPv4/IPv6 and user-supplied CIDRs.
Source ACL is restricted to AGENT_SUBNET. Squid CONNECT is intentionally
**not port restricted**; allowed public endpoints can use arbitrary TCP
ports. This widens egress and must be reviewed for production.
A forwarded request to a private endpoint is denied even when the
client tries HTTP CONNECT.

`AGENT_SUBNET` defaults to `auto`, not a fixed CIDR. A new network gets
an unused `/24`; an existing same-named network keeps its original CIDR.
`scripts/network-preflight.py` checks overlaps and validates reuse.
Never silently attach to an older unrestricted same-name network.

Change and test configuration:

```bash
# .env examples:
AGENT_SUBNET=auto
BLOCK_CIDRS=192.0.2.10/32,203.0.113.0/24
make preflight
make up
make network-check
```

IPv6 creation on the isolated Podman network is explicitly disabled.
Squid ACL still includes forbidden IPv6 destinations from outbound DNS.
Check whether rootless Netavark, host gateways or DNS helpers offer
reachability outside expected networks: `internal: true` is not a
complete substitute for a hardened host firewall.

## Migration from unrestricted network

The old project used `internal: false`. A stale network created with
that configuration must be stopped/recreated, not reused. The migration
target now explicitly removes **only that same project's old
unrestricted network** after stopping its containers and checking that
nothing remains attached; it does not remove any unrelated network.
Regular Compose `down` will no longer delete the new external network. If preflight
reports the subnet is **available** and no old project network is
present, `migrate-network` is unnecessary: simply `make up`.
A collision involving somebody else's network must be resolved by
choosing a distinct AGENT_SUBNET, **not** running migration.

```bash
# Save Codex sessions; backup persistent state before migrating.
make preflight
# ONLY if it rejects the old network owned by this Compose project
# as internal:false, and only after saving active work:
CONFIRM=YES make migrate-network
make preflight
make network-check
```

`migrate-network` calls Compose `down` without `-v` so it preserves
codex-state, agent-cache, postgres-data, serena-state. If other
projects have attached to the agent network, the network may remain
busy; inspect before taking any manual action. Do not force-remove a
network carrying another project's containers. Makefile startup does
not change image tags; shared images remain reusable.

## Verification on Debian 13

```bash
make up
make ps
make doctor
make network-check
podman network ls
make network-info
podman network inspect "$AGENT_NETWORK_NAME"   # on host; or use make network-info
```

Check that the agent has **one** internal network only, that Squid
has two, that no agent TCP ports are host-published, and the proxy
blocks private destinations. Test from a real LAN listener bound to
your host's nonloopback LAN IP; test VPN gateway, host publicly-routed
IP, metadata and IPv6. Closed listener ports alone cannot prove
packet isolation.

For command line/manual checks within `make shell`:

```bash
# Explicitly bypass environment proxy; must fail
curl --noproxy '*' -v --connect-timeout 3 https://1.1.1.1/
# Must work via Squid:
curl -I --noproxy '' -x "$HTTP_PROXY" https://example.com/
# Must return 403 via Squid; do NOT allow NO_PROXY to bypass proxy:
curl -I --noproxy '' -x "$HTTP_PROXY" http://127.0.0.1/
curl -I --noproxy '' -x "$HTTP_PROXY" http://169.254.169.254/
# Native TCP to allowed peer DB remains possible:
getent hosts postgres redis
```

**Squid ACL testing pitfall:** `NO_PROXY` (and `no_proxy`) includes
`127.0.0.1`. Even with an explicit `-x "$HTTP_PROXY"`, curl may
**bypass the proxy** for that address, then report HTTP `000` because
nothing is listening on the container's loopback. This does not prove
Squid allowed or denied the request. Use `--noproxy ''` to force a proxy
test, and `--noproxy '*'` only when deliberately testing the absence
of a direct route. `make network-check` uses both forms accordingly.

`NO_PROXY` includes local and peer service names so native local
clients connect to peers directly (the Squid ACL only applies to
connections that traverse Squid). Arbitrary peers attached to the
internal network can reach each other; do not attach untrusted projects.
DNS rebinding, domain alias changes, proxy implementation details,
non-HTTP protocols, rootless host gateway routing and compromised
proxy remain residual risks. No host Docker/Podman socket, host
network mode or broad home mount is supplied. For hostile workloads,
augment this with host-enforced firewall testing.
