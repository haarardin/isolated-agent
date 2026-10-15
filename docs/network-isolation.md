# Agent network isolation (rootless Podman)

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
with the per-project `AGENT_SUBNET`; `compose.web.yaml` adds Squid
and outbound network. The agent has one isolated network attachment
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

`AGENT_SUBNET` defaults to `10.89.71.0/24`, **not** the Webtop demo's
`10.89.70.0/24`. Each clone/Compose project needs a distinct subnet.
`scripts/network-preflight.py` rejects overlapping Podman subnets and
an existing same-name network which is not internal or has a wrong
subnet. Never silently reuse an older unrestricted network.

Change and test configuration:

```bash
# .env examples:
AGENT_SUBNET=10.89.72.0/24
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
that configuration must be stopped/recreated, not reused.

```bash
# Save Codex sessions; backup persistent state before migrating.
make preflight  # expected to fail if old network is unrestricted
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
