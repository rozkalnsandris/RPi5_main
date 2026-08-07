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
same-host connector is allowed only as a temporary update or migration canary.
True host-level high availability requires another physical host or failure
domain.

## Application ownership boundary

The former application-owned connector model is permanently retired. No
application Compose file, deploy helper, rollback helper or environment file may
own the shared connector or its tunnel credential.

A future application change that attempts to introduce an app-owned
`cloudflared` service, tunnel token dependency, connector readiness gate,
connector restart/reconciliation or connector rollback is an architecture
regression and must fail review.

## Current published-hostname classes

The route list is remotely managed. The current reviewed policy classes are:

| Hostname | Origin | Class | External access policy |
|---|---|---|---|
| `rozkalns.net` | `http://127.0.0.1:8088` | public | no Access login |
| `tech.rozkalns.net` | `http://127.0.0.1:8089` | public | no Access login |
| `deals.rozkalns.net` | `http://192.168.0.180:9128` | private application | Cloudflare Access |
| `hermes.rozkalns.net` | `http://192.168.0.180:9119` | admin/private | Cloudflare Access |
| `portainer.rozkalns.net` | `http://192.168.0.180:9000` | admin | Cloudflare Access |
| `grafana.rozkalns.net` | `http://192.168.0.180:3030` | admin | Cloudflare Access |
| `ha.rozkalns.net` | `http://192.168.0.180:8123` | admin | Cloudflare Access |
| `adguard.rozkalns.net` | `http://192.168.0.180:3080` | admin | Cloudflare Access |
| `kuma.rozkalns.net` | `http://192.168.0.180:3001` | admin | Cloudflare Access |
| `prometheus.rozkalns.net` | `http://192.168.0.180:9090` | admin | Cloudflare Access |

The two public sites that do not require direct LAN access now use loopback-only
origins on the RPi5:

- CV/public apex: `127.0.0.1:8088`;
- Hermes Tech: `127.0.0.1:8089`.

Both corresponding LAN UFW allow rules were removed only after loopback bind,
public HTTP and connector-readiness verification passed.

`hermes.rozkalns.net` is private by default. It must not be made public unless
there is an explicit product requirement and a separate review of what the
service exposes.

## Access grouping rule

Do **not** protect all `*.rozkalns.net` with one broad wildcard Access policy.
Public and private hostnames share the zone, and a broad wildcard can trap
intentionally public sites behind Access.

Use exact hostnames, or a deliberately reviewed narrow grouping, for private
applications. If Cloudflare account-level Access enforcement is enabled, first
create explicit applications or public exemptions for every intentionally public
hostname.

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
connections to Cloudflare on TCP/UDP port `7844`, plus normal DNS/HTTPS required
by the host.

UFW remains useful for host-native and intentionally LAN-facing services such as
SSH, DNS, MQTT and reviewed local administration paths.

### Docker warning

Docker-published ports must not rely on UFW as their primary exposure control.
Docker creates NAT/filter rules and published container traffic can be diverted
before UFW's normal host `INPUT` rules are evaluated.

Exposure is therefore controlled in this order:

1. bind the service to the narrowest host address that satisfies the use case;
2. use Cloudflare Access for externally reachable private/admin hostnames;
3. keep UFW as defense in depth for host/LAN traffic;
4. use Docker/firewall-specific forwarding policy only for a real routed-port
   requirement.

### Binding policy

- Public applications that need no direct LAN access should use a loopback
  publish such as `127.0.0.1:PORT:CONTAINER_PORT` and a loopback Tunnel origin.
- Private/admin services may retain a `192.168.0.180` LAN binding when local
  break-glass access is intentionally desired; external access remains behind
  Cloudflare Access.
- Wildcard Docker publishes (`0.0.0.0` / `[::]`) are not accepted for
  Tunnel-only origins unless explicitly justified.

The CV `8088` and Hermes Tech `8089` public origins are the first completed
examples of this loopback-only policy.

## UFW cleanup status

Obsolete Tunnel-specific Docker-subnet rules have been removed. LAN rules are
not removed as a batch; each rule is retained or removed according to whether
direct LAN access is an intentional requirement.

Current policy:

- keep LAN SSH/DNS/MQTT rules while those LAN services are intentionally used;
- keep reviewed LAN admin rules where local break-glass access is desired;
- CV `8088/tcp`: no direct LAN allow rule; loopback-only origin;
- Hermes Tech `8089/tcp`: no direct LAN allow rule; loopback-only origin.

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

This ownership statement supersedes historical instructions that assumed the
shared connector belonged to an individual application.
