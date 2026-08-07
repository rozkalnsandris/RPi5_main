# V18 Cloudflare LAN-origin audit contract

## Status

**Source review in progress; production audit not yet executed.**

V18 inventories the remaining Cloudflare origins that still target the RPi5 LAN address before any further loopback hardening decision.

Merging V18 performs no production mutation.

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

## Privacy and secret boundary

V18 must not read or print:

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

The audit can establish technical facts such as wildcard/LAN/loopback binding, runtime ownership evidence and existing firewall exposure. It cannot infer a human policy requirement merely from host state.

After the production audit, each origin must be classified with an explicit decision into one of:

1. **keep LAN break-glass** — direct LAN access is intentionally required;
2. **loopback migration candidate** — direct LAN access is not required and the service can be reviewed for a CV/Tech-style loopback cutover;
3. **application-specific investigation required** — ownership, protocol or operational constraints require a separate investigation first.

No origin may be migrated merely because it is technically reachable on loopback.

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

## Completion criterion

V18 is complete only when all eight origins have a verified production inventory and an explicit keep/candidate/investigate classification. The audit itself performs no deployment or exposure change.
