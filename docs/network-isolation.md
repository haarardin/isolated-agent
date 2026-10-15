# Agent network isolation (rootless Podman)

For the exact ordered commands to start the filtered online agent and
pair an Android device, see
[REMOTE-START.md](REMOTE-START.md). The network migration below is
**conditional**, not part of a fresh installation.

## Network per Compose project: create or safely reuse

Every deployment has a **stable, project-specific internal network name**:

```text
<COMPOSE_PROJECT_NAME>_isolated-dev
```

For example, `ai-orders_isolated-dev` and
`ai-billing_isolated-dev` are **two different** Podman networks.
Use a distinct `COMPOSE_PROJECT_NAME` for each independent project:
otherwise the same name intentionally means the same network **and the
same Compose-scoped named volumes**.

`AGENT_SUBNET=auto` is the default. Before starting any containers:

1. `make preflight` inspects Podman networks **without modifying them**.
2. `make network-ensure` searches for the expected name.
3. If the name exists, it validates `internal: true`, bridge driver,
   IPv4-only configuration, project labels (if present), and the subnet.
   A valid network is **reused**. A foreign, unrestricted or mismatched
   network causes an error, not silent attachment.
4. If missing, it selects a free `/24` from `10.203.0.0/16` using a
   stable project-name hash and collision checks, then creates the
   network with rootless `podman network create --internal`.
5. The chosen network and CIDR are saved in ignored
   `.state/network.json`; Squid's source ACL is generated from the
   **actual** network subnet, not from a hardcoded default.

```bash
# .env: independent project identity and automatic subnet:
COMPOSE_PROJECT_NAME=ai-orders
AGENT_SUBNET=auto

make network-info      # check plan/existing network; does NOT create
make network-ensure    # create if missing, reuse if it exists safely
make up                # also calls network-ensure automatically
podman network inspect ai-orders_isolated-dev
```

For a specific subnet, set `AGENT_SUBNET=10.210.31.0/24` and rerun
preflight. This **does not move** an already created network: if its
CIDR differs, startup fails until you intentionally migrate or change
the configuration. The auto-allocator only inspects **Podman** networks;
also check host LAN/VPN routes separately and choose a non-overlapping
explicit CIDR if necessary.

The `isolated-dev` network is `external: true` in Compose: **Compose
does not own its lifecycle**. `make down` and normal container
recreation leave it intact for other explicitly attached containers.
There is no automatic deletion just because the agent stops.
`outbound` remains a separate Compose-managed network for Squid only.
A shared network has shared L2/L3 access for attached containers;
never connect independent/untrusted project containers to it merely
because a name matches.

## Topology

```text
Codex agent (internal-only network, AGENT_SUBNET)
     |             |                 |
 /workspace     postgres          redis
     |
     +----> squid:3128 (internal + outbound networks)
                    |
                Internet
```

Only Squid is dual-homed. `compose.yaml` has `internal: true`
with the project's resolved `AGENT_SUBNET`; `compose.web.yaml` adds Squid
and outbound network. The internal network is prepared by a host script
and declared `external: true` in Compose, so the `internal` property
is checked in **Podman inspect**, not inferred from the external Compose stanza. The agent has one isolated network attachment
in both modes; `HTTP_PROXY` alone is NOT a security boundary.

```bash
make up              # filtered web, Squid on isolated + outbound
make offline         # remove Squid container, no Internet gateway
make up-example      # filtered web + postgres/redis
make offline-example # offline with postgres/redis
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

`AGENT_SUBNET` defaults to `auto`, not a shared fixed CIDR. A fresh
project receives a unique free `/24` from the allocation pool.
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
podman network inspect <project>_isolated-dev
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
curl -I --noproxy '' -x http://squid:3128 https://example.com/
# Must return 403 via Squid; do NOT allow NO_PROXY to bypass proxy:
curl -I --noproxy '' -x http://squid:3128 http://127.0.0.1/
curl -I --noproxy '' -x http://squid:3128 http://169.254.169.254/
# Native TCP to allowed peer DB remains possible:
getent hosts postgres redis
```

**Squid ACL testing pitfall:** `NO_PROXY` (and `no_proxy`) includes
`127.0.0.1`. Even with an explicit `-x http://squid:3128`, curl may
**bypass the proxy** for that address, then report HTTP `000` because
nothing is listening on the container's loopback. This does not prove
Squid allowed or denied the request. Use `--noproxy ''` to force a proxy
test, and `--noproxy '*'` only when deliberately testing the absence
of a direct route. `make network-check` uses both forms accordingly.

`NO_PROXY` includes PostgreSQL/Redis service names so native local
clients connect to peers directly (the Squid ACL only applies to
connections that traverse Squid). Arbitrary peers attached to the
internal network can reach each other; do not attach untrusted projects.
DNS rebinding, domain alias changes, proxy implementation details,
non-HTTP protocols, rootless host gateway routing and compromised
proxy remain residual risks. No host Docker/Podman socket, host
network mode or broad home mount is supplied. For hostile workloads,
augment this with host-enforced firewall testing.
