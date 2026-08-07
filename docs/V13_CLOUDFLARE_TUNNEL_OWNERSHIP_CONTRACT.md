# V13 Cloudflare Tunnel ownership contract

## Purpose

V13 moves ownership of the shared `rpi5-tunnel` connector out of the
`rozkalns-cv` application lifecycle and into `RPi5_main` as host-wide
infrastructure. The tunnel remains remotely managed in Cloudflare; this
repository owns only the RPi5 connector runtime, validation, operating
procedure, monitoring contract and rollback boundary.

The immediate objective is a no-downtime migration from the existing Docker
connector to one host-level systemd connector while keeping Raspberry Pi 5
resource usage small.

## Why this is separate from V12

V12 deliberately excludes systemd units and Cloudflare until each subsystem has
its own reviewed source/installed mapping, validation and rollback contract.
V13 is that contract for Cloudflare Tunnel. It does not weaken or bypass the
V12 root boundary and it does not add the Cloudflare unit to the V12 target
manifest implicitly.

## Incident boundary

The shared connector has historically been a service in the CV Docker Compose
project even though it serves multiple unrelated host applications. A CV
production deployment can therefore restart, replace or roll back the sole
Cloudflare connector. That ownership coupling already caused an incident in
which a connector replacement lost its previously established Cloudflare
session and public applications returned 502/530 while rollback could not
restore the old session.

The permanent invariant is:

> Application repositories deploy only their application. No application
> deployment, rollback or image reconciliation may control the shared
> Cloudflare connector.

## Cloudflare management model

`rpi5-tunnel` remains a remotely-managed tunnel. Published application routes,
DNS associations, origin parameters and Cloudflare Access policy stay in the
Cloudflare control plane and can later be imported into reviewed Terraform.
The RPi5 does not become the authoritative store for route configuration and no
local ingress `config.yml` is introduced.

The connector uses a tunnel token only. The token is never tracked in Git,
printed by validation, embedded in the systemd unit, passed on the command line
or written into deployment evidence.

## Current published applications

The Cloudflare dashboard inventory reviewed on 2026-08-07 contains:

| Hostname | Current origin | Class |
|---|---|---|
| `rozkalns.net` | `http://172.19.0.10:80` | public |
| `portainer.rozkalns.net` | `http://192.168.0.180:9000` | admin / Access |
| `grafana.rozkalns.net` | `http://192.168.0.180:3030` | admin / Access |
| `ha.rozkalns.net` | `http://192.168.0.180:8123` | admin / Access |
| `adguard.rozkalns.net` | `http://192.168.0.180:3080` | admin / Access |
| `kuma.rozkalns.net` | `http://192.168.0.180:3001` | admin / Access |
| `hermes.rozkalns.net` | `http://192.168.0.180:9119` | application |
| `prometheus.rozkalns.net` | `http://192.168.0.180:9090` | admin / Access |
| `tech.rozkalns.net` | `http://192.168.0.180:8089` | public |
| `deals.rozkalns.net` | `http://192.168.0.180:9128` | Access-protected |

The apex origin was previously Docker-only `http://cv:80`. It was changed to
the temporary direct container address only after proving that both the host
and the old connector network namespace could reach it and five consecutive
public checks remained HTTP 200. `172.19.0.10` is not a stable final origin and
must be removed after the host connector is established.

## Host connector source

The reviewed unit source is:

```text
ops/systemd/cloudflared.service
```

The initial binary identity is intentionally the same release already proven
by the Docker connector:

```text
/usr/local/libexec/cloudflared/2026.7.3/cloudflared
SHA256 65259e652a7bea08bf5df603233ab22b8bf3116af8df9f9206209af6a1b955c0
```

`/usr/local/bin/cloudflared` may point to the versioned binary for operator
convenience, but the service uses the exact versioned path so an unrelated
symlink change cannot silently replace the running connector.

Automatic `cloudflared` self-update is disabled. Version changes require a
reviewed update, exact binary checksum verification, a temporary edge-ready
replica/canary, and rollback availability.

## Secret handling

The authoritative host token file is:

```text
/etc/cloudflared/rpi5-tunnel.token
```

Required metadata:

- owner `root:root`;
- mode `0600`;
- non-empty token content;
- never tracked in Git.

The unit uses systemd `LoadCredential=` so the dynamically allocated service
user does not need direct permission to the root-only source file. `cloudflared`
reads the systemd-provided credential with `--token-file` rather than exposing
the token in `ExecStart` or process arguments.

The old CV token source must remain untouched until the migration has passed
all cutover and rollback gates. It is removed from the CV application only
after the old Docker connector is retired and the application repo no longer
owns Cloudflare runtime state.

## Systemd runtime model

The host connector:

- starts only after network-online;
- runs as a `DynamicUser`;
- has no Linux capabilities;
- receives only the systemd credential copy of the tunnel token;
- uses a private runtime directory;
- has a read-only system view and no home access;
- exposes Prometheus metrics only on `127.0.0.1:20241`;
- disables automatic updates;
- restarts on process failure;
- uses bounded task and memory controls;
- is biased against OOM termination because host ingress is critical.

The unit deliberately retains normal outbound IPv4/IPv6 networking. It does not
use `PrivateNetwork=`, IP allowlists, or aggressive syscall filtering because
Cloudflare edge addresses and origin connections are part of the connector's
normal function and the migration must not introduce an availability hazard.

## Resource policy

Only one host connector is intended to remain continuously active on this
RPi5. A second connector on the same RPi5 is temporary for migration or an
update canary, not permanent high availability. True host-level redundancy
would require a second physical host/network failure domain.

The service starts with `MemoryHigh=96M`, `MemoryMax=128M`, `TasksMax=64` and no
CPU quota. These limits leave substantially more headroom than the historical
~20 MiB connector working set without allowing accidental unbounded growth.
CPU quota is avoided because throttling ingress during a traffic or reconnect
spike would trade resource protection for availability.

## Migration gates

The old Docker connector remains online until every preceding gate passes.

1. Read-only host, Docker, network, UFW and public-route audit — complete.
2. Cloudflare published-application inventory — complete.
3. Existing Docker connector edge readiness 4/4 — complete.
4. Temporary shared apex origin reachable from both old connector and host — complete.
5. Public apex route verification after temporary origin change — complete.
6. Exact `cloudflared 2026.7.3` ARM64 host binary and SHA256 verification — complete.
7. Root-only token file installation without secret disclosure — complete.
8. Review and merge this V13 source/contract through CI.
9. Install the exact reviewed unit without starting it and verify file identity.
10. Start the host connector while the old Docker connector remains online.
11. Require local host metrics/diagnostics to show four active edge connections.
12. Confirm both connectors are healthy in the Cloudflare tunnel view.
13. Verify every published application end-to-end; Access-protected endpoints
    are checked separately for expected Access redirect and local origin health.
14. Stop only the old Docker connector and repeat connector and application checks.
15. Observe the host connector before removing any rollback source.
16. Remove Cloudflare service/image/reconciliation ownership from `rozkalns-cv`.
17. Replace the temporary apex container IP with a stable host-level origin.
18. Remove obsolete Cloudflared-specific Docker-subnet UFW rules only after the
    new stable origin and host connector are verified.
19. Add Prometheus/Grafana/Uptime Kuma monitoring and alerting.
20. Document tested token rotation, binary update canary and disaster recovery.
21. Evaluate a reviewed Terraform import of Cloudflare control-plane state only
    after runtime migration is stable.

## Edge-readiness contract

Process state alone is insufficient. `active (running)` does not prove that a
connector is registered with Cloudflare.

A connector is accepted only when its local diagnostic/metrics endpoint proves
four active Cloudflare edge connections. Migration and updates also require
external application checks. No old connector is stopped based only on
systemd/Docker process state.

## Rollback

Before the old Docker connector is removed, rollback is simply:

1. stop/disable the new host service if it is unhealthy;
2. verify the old Docker connector remains 4/4 edge-ready;
3. restore the last known-good Cloudflare route only if the route itself was
   changed during that transaction;
4. verify public endpoints again.

After the Docker connector has been retired, the previous exact host binary and
reviewed unit remain the runtime rollback assets. A binary update must never
replace the previous versioned binary in place.

Token rotation is a separate operation. It must not be combined with the
initial ownership migration. A rotated old token cannot establish new
connections even though an already-established connector may continue serving
until restarted, so rotation requires a separately proven connector using the
new token before the old session is touched.

## Deployment boundary

Merging V13 performs no production change. It does not install, enable, start,
stop or restart `cloudflared`, change Cloudflare routes, edit UFW, remove the CV
connector, rotate a token or change application origins. Each live transition
is separately confirmed and verified against the migration gates above.
