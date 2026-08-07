# V13 Cloudflare Tunnel ownership contract

## Status

**Migration complete — 2026-08-07.**

`RPi5_main` is the only repository that owns the shared RPi5 Cloudflare
connector runtime. Application repositories own only their applications.

The permanent invariant is:

> Application repositories may verify their own local and public endpoints, but
> they must never install, start, stop, restart, replace, canary, reconcile,
> roll back or hold credentials for the shared Cloudflare connector.

## Authoritative runtime

The shared remotely-managed tunnel is connected by one host-level systemd
service:

- unit: `cloudflared.service`;
- source owner: `rozkalnsandris/RPi5_main`;
- binary: exact versioned `cloudflared` under `/usr/local/libexec/cloudflared/`;
- operator symlink: `/usr/local/bin/cloudflared`;
- token source: `/etc/cloudflared/rpi5-tunnel.token`;
- token metadata: `root:root`, mode `0600`;
- credential delivery: systemd `LoadCredential=` plus `--token-file`;
- metrics: loopback-only `127.0.0.1:20241`;
- expected healthy connector state: four active edge connections.

The tunnel is remotely managed in Cloudflare. Published-application routes,
DNS associations and Cloudflare Access policy remain control-plane state. No
local tunnel ingress `config.yml` is authoritative on the RPi5.

Only one connector remains continuously active on this physical RPi5. A second
same-host connector is allowed only as a temporary update/migration canary.
True host-level high availability requires another physical host/failure domain.

## Retired application-owned model

The former CV-owned Docker connector model is permanently retired. No
application Compose file, deploy helper, rollback helper or environment file may
own the shared connector or its tunnel credential.

A future application change that attempts to introduce an app-owned
`cloudflared` service, tunnel token dependency, connector readiness gate,
connector restart/reconciliation or connector rollback is an architecture
regression and must fail review.

## Current published-hostname classes

The route list is remotely managed. The current policy classes are:

| Hostname | Origin | Class | External access policy |
|---|---|---|---|
| `rozkalns.net` | `http://127.0.0.1:8088` | public | no Access login |
| `tech.rozkalns.net` | `http://192.168.0.180:8089` | public | no Access login |
| `deals.rozkalns.net` | `http://192.168.0.180:9128` | private application | Cloudflare Access |
| `hermes.rozkalns.net` | `http://192.168.0.180:9119` | admin/private | Cloudflare Access |
| `portainer.rozkalns.net` | `http://192.168.0.180:9000` | admin | Cloudflare Access |
| `grafana.rozkalns.net` | `http://192.168.0.180:3030` | admin | Cloudflare Access |
| `ha.rozkalns.net` | `http://192.168.0.180:8123` | admin | Cloudflare Access |
| `adguard.rozkalns.net` | `http://192.168.0.180:3080` | admin | Cloudflare Access |
| `kuma.rozkalns.net` | `http://192.168.0.180:3001` | admin | Cloudflare Access |
| `prometheus.rozkalns.net` | `http://192.168.0.180:9090` | admin | Cloudflare Access |

`hermes.rozkalns.net` is private by default. It must not be made public unless
there is an explicit product requirement and a separate review of what the
service exposes.

### Access grouping rule

Do **not** protect all `*.rozkalns.net` with one broad wildcard Access policy.
Public and private hostnames share the zone, and a broad wildcard previously
risked trapping public sites behind Access.

Use exact hostnames (or a deliberately reviewed narrow grouping) for private
applications. If Cloudflare's account-level **Require Access protection**
feature is enabled, first create explicit Access applications or public
exemptions for every intentionally public hostname so the public sites are not
blocked.

Public set:

- `rozkalns.net`;
- `tech.rozkalns.net`.

Private/admin set:

- `deals.rozkalns.net`;
- `hermes.rozkalns.net`;
- `portainer.rozkalns.net`;
- `grafana.rozkalns.net`;
- `ha.rozkalns.net`;
- `adguard.rozkalns.net`;
- `kuma.rozkalns.net`;
- `prometheus.rozkalns.net`.

## Host firewall policy

UFW remains enabled as a host firewall. Cloudflare Tunnel does not replace the
host firewall.

Cloudflare Tunnel itself is outbound-only. A normal connector needs no inbound
firewall opening for Internet traffic. The host must be able to make outbound
connections to Cloudflare on TCP/UDP port `7844` (and normal DNS/HTTPS needed by
the host). With UFW's normal allow-outgoing policy, no inbound Tunnel-specific
rule is required.

UFW is still useful for host-native and LAN-facing services such as SSH, DNS,
MQTT and intentionally retained LAN administration paths.

### Docker warning

Docker-published ports must not rely on UFW as their primary exposure control.
Docker creates its own NAT/filter rules and published container traffic can be
diverted before UFW's normal host `INPUT` rules are evaluated.

Therefore exposure is controlled in this order:

1. bind the service to the narrowest host address that satisfies the use case;
2. use Cloudflare Access for externally reachable private/admin hostnames;
3. keep UFW as defense-in-depth for host/LAN traffic;
4. use Docker/firewall-specific forwarding policy only when a real routed-port
   requirement exists.

### Binding policy

- Public applications that need no direct LAN access should prefer a loopback
  publish such as `127.0.0.1:PORT:CONTAINER_PORT` and a loopback Tunnel origin.
- Private/admin services may retain a `192.168.0.180` LAN binding when local
  break-glass access is intentionally desired; external access remains behind
  Cloudflare Access.
- Wildcard Docker publishes (`0.0.0.0` / `[::]`) are not accepted for
  Tunnel-only origins unless explicitly justified.

The CV origin is the first target for this hardening: its public route already
uses `127.0.0.1:8088`, so the Docker publish should also become loopback-only.

## UFW cleanup after connector migration

The old rules that allowed host service ports specifically from Docker subnet
`172.19.0.0/16` for the former connector are obsolete. The host-level connector
does not originate from that Docker network. Those Tunnel-specific rules should
be removed after a numbered-rule preflight and followed immediately by local
origin, connector 4/4 and public endpoint verification.

LAN rules are **not** removed as a batch. Each LAN rule is retained or removed
based on whether direct LAN access is intentionally required for that service.

In particular:

- keep LAN SSH/DNS/MQTT rules while those LAN services are intentionally used;
- keep LAN admin rules where local break-glass access is desired;
- remove the CV `8088/tcp` LAN rule after CV is bound to loopback only;
- review the public Hermes Tech `8089` wildcard publish separately before
  changing its Cloudflare origin or LAN rule.

## Connector readiness and updates

`active (running)` alone is not sufficient evidence of Tunnel health. Normal
verification requires:

- systemd service active/enabled;
- expected exact binary/unit identity;
- four active edge connections from the loopback metrics endpoint;
- local origin health for affected applications;
- external public/Access-path verification as appropriate.

A `cloudflared` binary update must keep the previous exact version available and
prove a temporary connector/canary is edge-ready before replacing the current
working session. Token rotation is a separate operation and must not be combined
casually with application deployment or binary replacement.

## Application repository contract

Every RPi5 application repository should document this boundary:

- shared ingress runtime owner: `RPi5_main`;
- route/Access owner: Cloudflare control plane plus host infrastructure review;
- app deploy owner: application only;
- app deploy may check public health but may not manipulate shared ingress;
- no shared Tunnel credential may be committed, copied into app runtime, passed
  through app Compose, or written into app deployment evidence.

This ownership statement supersedes all historical incident instructions that
assumed the connector lived inside the CV Compose project.
