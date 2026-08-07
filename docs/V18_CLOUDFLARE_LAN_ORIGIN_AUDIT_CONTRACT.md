# V18 Cloudflare LAN-origin audit contract

## Status

**Production read-only audit complete — 2026-08-07.**

V18 inventories the remaining Cloudflare origins that still target the RPi5 LAN address before any further loopback hardening decision.

Merging V18 performed no production mutation. The later production audit was separately executed as a read-only action and completed with no-mutation evidence.

## Reviewed route scope

V18 is anchored to the V13 reviewed route inventory and covers exactly these eight origins:

| Hostname | Current reviewed origin | Class |
|---|---|---|
| `deals.rozkalns.net` | `http://192.168.0.180:9128` | private application |
| `hermes.rozkalns.net` | `http://192.168.0.180:9119` | admin/private |
| `portainer.rozkalns.net` | `http://192.168.0.180:9000` | admin |
| `grafana.rozkalns.net` | `http://192.168.0.180:3030` | admin |
| `ha.rozkalns.net` | `http://192.168.0.180:8123` | admin |
| `adguard.rozkalns.net` | `http://192.168.0.180:3080` | admin |
| `kuma.rozkalns.net` | `http://192.168.0.180:3001` | admin |
| `prometheus.rozkalns.net` | `http://192.168.0.180:9090` | admin |

The authoritative Cloudflare route list is remotely managed. V18 does not query, create, update or delete Cloudflare routes or Access policies.

## Reviewed audit operator

Authoritative read-only operator:

```text
ops/bin/audit-cloudflare-lan-origins
```

The operator requires root only because listener/process metadata and UFW status can require elevated read access. Root execution does not authorize mutation.

For every reviewed port it collects only allowlisted exposure metadata:

- listener bind class from `ss` (`loopback`, `lan-specific`, `wildcard`, `mixed`, `other`, or `none`);
- Docker container name if `docker port` exposes the reviewed host port;
- listener process identity reported by `ss`;
- matching UFW LAN rule text for the reviewed port, if present;
- TCP reachability from the host to `127.0.0.1:PORT`;
- TCP reachability from the host to `192.168.0.180:PORT`;
- shared `cloudflared.service` active/enabled state, PID evidence, and HA readiness 4/4.

The operator prints its result to stdout only. It does not create evidence files or read application payloads.

## Production audit evidence

The production audit completed PASS on 2026-08-07 against exact repository main `7832285e0ecf64def73ccc0a30138a18163afafb`.

No-mutation evidence:

- V18 regression: PASS;
- Cloudflare PID before/after: `878` / `878`;
- Cloudflare HA: 4/4;
- UFW SHA256 before/after: `5daffa3993d7857554bc9db84c3c617c1d6ed6a56816df4266d1a9bd524e08cf`;
- container identity SHA256 before/after: `3b360f4d6ef5a7ee36f59ce20b63fad85973ceae1853885b45523aa6aec2db16`;
- operator marker: `V18_CLOUDFLARE_LAN_ORIGIN_AUDIT=PASS`;
- wrapper markers: `V18_NO_MUTATION_PROOF=PASS` and `V18_PRODUCTION_LAN_ORIGIN_AUDIT=PASS`.

Observed inventory:

| Hostname | Port | Bind | Docker published-port owner | UFW LAN allow | Loopback TCP | LAN TCP |
|---|---:|---|---|---|---|---|
| `deals.rozkalns.net` | 9128 | LAN-specific | `hermes-deals-web-1` | none | closed | open |
| `hermes.rozkalns.net` | 9119 | LAN-specific | none identified | present | closed | open |
| `portainer.rozkalns.net` | 9000 | LAN-specific | `portainer` | present | closed | open |
| `grafana.rozkalns.net` | 3030 | LAN-specific | `grafana` | present | closed | open |
| `ha.rozkalns.net` | 8123 | wildcard | none identified | present | open | open |
| `adguard.rozkalns.net` | 3080 | wildcard | none identified | present | open | open |
| `kuma.rozkalns.net` | 3001 | wildcard | none identified | present | open | open |
| `prometheus.rozkalns.net` | 9090 | LAN-specific | `prometheus` | present | closed | open |

## Privacy and secret boundary

V18 did not read or print:

- Docker container environments;
- `.env` files;
- Cloudflare tunnel tokens or credentials;
- application configuration files;
- authentication cookies, headers or credentials;
- database contents;
- DNS query logs or client identities;
- application logs;
- HTTP response bodies.

TCP probes open a connection only; they do not submit application requests.

## Forbidden actions

V18 must not:

- run Docker lifecycle mutations (`run`, `create`, `start`, `stop`, `restart`, `rm`, `rename`, `pull`, image/system prune, or image removal);
- run systemd lifecycle mutations (`start`, `stop`, `restart`, `enable`, `disable`, `mask`, `reload`, reboot or poweroff);
- edit UFW rules;
- edit Cloudflare Tunnel routes or Access;
- deploy or modify any application;
- modify bind addresses, published ports, Compose files or systemd units;
- write to production application directories;
- reboot or shut down the host.

## Interpretation boundary

The audit establishes technical facts such as wildcard/LAN/loopback binding, runtime ownership evidence and existing firewall exposure. It cannot infer a human policy requirement merely from host state.

The reviewed infrastructure policy decision after the audit is:

| Hostname | Classification | Rationale |
|---|---|---|
| `deals.rozkalns.net` | **loopback migration candidate** | private app; LAN-specific Docker publish; no matching UFW LAN allow rule; no reviewed break-glass requirement established |
| `hermes.rozkalns.net` | **keep LAN break-glass** | admin/private service with an existing reviewed LAN administration rule |
| `portainer.rozkalns.net` | **keep LAN break-glass** | core host administration path; local access remains useful when shared ingress is unavailable |
| `grafana.rozkalns.net` | **keep LAN break-glass** | local observability/admin access remains useful during tunnel or external-access incidents |
| `ha.rozkalns.net` | **keep LAN break-glass** | LAN-local Home Assistant administration must remain available independently of Cloudflare |
| `adguard.rozkalns.net` | **keep LAN break-glass** | LAN-local DNS administration must remain available independently of Cloudflare |
| `kuma.rozkalns.net` | **keep LAN break-glass** | local monitoring access remains useful when external ingress is impaired |
| `prometheus.rozkalns.net` | **keep LAN break-glass** | local metrics administration/diagnostics remains useful during ingress incidents |

This classification does not make any production exposure change. It records the operational policy for the next step.

## Migration boundary

Any actual origin change is outside V18. A future migration must use a separate issue and preserve the safe order already proven for CV and Hermes Tech:

1. identify authoritative runtime ownership;
2. prove loopback origin health while the existing listener still works;
3. change the Cloudflare route only under an explicit reviewed cutover;
4. verify the public/Access path;
5. narrow the runtime bind;
6. verify direct LAN failure where LAN access is being retired;
7. remove the matching UFW rule only after the loopback-only runtime is proven;
8. retain an explicit rollback path until post-change stability is established.

For the current inventory, only Deals `9128` advances as a loopback-migration candidate. Its actual migration requires a separate issue in the application/runtime ownership context.

## Completion criterion

V18 is complete: all eight origins have a verified production inventory and an explicit keep/candidate classification. The audit itself performed no deployment or exposure change.
