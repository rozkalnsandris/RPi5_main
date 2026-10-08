# Phase 7 automated ingress drift audit v1

Status: **source-defined / read-only / no runtime authority**  
Roadmap: `RPi5_main#60`  
Implementation: `RPi5_main#903`  
Machine contract: `ops/contracts/ingress-drift-audit-v1.json`

## Purpose

Phase 7 turns the one-off Phase 6 exposure review into a bounded repeatable drift check.

The audit compares two existing trust surfaces against the canonical ingress registry:

1. Cloudflare Tunnel state through the existing reviewed GET-only client and route classifier;
2. RPi5 listener, Docker publish, firewall and connector-health metadata through a bounded host collector.

The combined result is either:

- `PASS` — the reviewed ingress exposure still matches source policy;
- `DRIFT` — one or more public-safe drift classes were detected;
- `BLOCKED` — the audit could not obtain or validate the required read-only evidence.

The audit never remediates drift.

## Reuse-first architecture

Phase 7 deliberately does **not** add another Cloudflare API client, mutation workflow or credential bridge.

`scripts/ingress_drift_audit.py` imports and reuses `CloudflareGetClient`, registry parsing and Tunnel route-classification helpers from `scripts/cloudflare_zero_trust_reconcile.py`.

Phase 7 deliberately narrows that existing client to four GET surfaces: account-owned token verification at `GET /accounts/{account_id}/tokens/verify`, exact-name Tunnel discovery, Tunnel metadata and Tunnel configuration. It does **not** enumerate Access applications, policies, organizations or selector values. This keeps the audit inside the route/exposure scope while avoiding a second API implementation.

The API token is accepted only through stdin and is never accepted from `CLOUDFLARE_API_TOKEN` in the child environment. The account binding comes from the fixed root-owned Tunnel capability boundary. The Tunnel ID is not separately configured: the audit discovers exactly one remotely-managed `rpi5-tunnel` by name and never emits the account or Tunnel identifier.

The host side is implemented by `scripts/ingress_drift_host.py`.

## Canonical target derivation

The exact service set comes from `ops/contracts/ingress-registry-v1.json`.

Runtime probe coordinates are not emitted in evidence. They are derived from already-reviewed source contracts:

- ADMIN targets: `ops/contracts/admin-zone-remaining-infra-verifier-v1.json`;
- PRIVATE target: `ops/contracts/private-zone-verification-v1.json`;
- PUBLIC targets: the small Phase 7 `public_probe_targets` list, with a source reference for every probe coordinate.

The collector fails closed unless the resulting target set exactly equals the RPi5-hosted ingress registry service set.

### Weather PUBLIC follow-up (#911)

The first successful owner-authorized Phase 7 run on `RPi5_main@cef629f7ee36432771ef489e7085a62b83629064` returned one Cloudflare inventory drift reason: `unclassified_tunnel_hostname:weather.rozkalns.net`. The other 12 registered services and shared connector health passed, and the audit performed no mutation.

#911 adds Weather to the source policy as a PUBLIC service with desired loopback origin and no LAN break-glass. It deliberately does **not** claim a current route-origin value: the registry keeps `current_origin_class=unknown` until bounded runtime evidence establishes it. The Phase 7 public probe target is derived from the reviewed Weather public Compose source at `15d4ce929b442c322a859161501e1db7ae857ed2`.

This classification does not normalize the current Weather publish shape. Docker Compose documents that a published port without `host_ip` binds to all interfaces, while Cloudflare Tunnel documents same-host published applications using local service addresses such as `localhost`. Therefore a wildcard Weather listener or Docker publish remains `DRIFT` against the loopback target and requires a separate remediation issue / LIVE authorization.

References:
- https://developers.cloudflare.com/tunnel/get-started/
- https://developers.cloudflare.com/tunnel/concepts/routing/
- https://docs.docker.com/reference/compose-file/services/#ports

## Drift classes

The combined audit covers the Phase 7 checklist from #60:

- unknown or unclassified Cloudflare Tunnel hostname;
- missing, duplicate or malformed Tunnel route inventory;
- route origin class differing from source policy;
- listener bind differing from source policy;
- Docker publish differing from source policy;
- wildcard Docker publish on a reviewed ingress target;
- expected loopback listener missing;
- expected ADMIN LAN break-glass missing;
- ADMIN LAN exposure broadened beyond the reviewed boundary;
- firewall exposure differing from policy;
- `cloudflared.service` not active/enabled;
- connector edge-connection count differing from the reviewed healthy value.

ADMIN host-native wildcard listeners are not automatically drift. They are accepted only for services whose source policy retains LAN break-glass and whose firewall exposure remains classified `lan-only`. Wildcard **Docker publishing** remains drift.

## Host observation boundary

The host collector may use only:

- exact Git source checks;
- `ip` JSON route/address metadata;
- `ss -H -lnt`;
- `docker ps --format '{{.Ports}}'`;
- `sudo -n ufw status numbered`;
- `systemctl is-active cloudflared.service`;
- `systemctl is-enabled cloudflared.service`;
- GET of the loopback Cloudflare metrics endpoint.

The collector does not request process identities and does not read container identities. Docker is queried only for the formatted publish string.

Forbidden surfaces include:

- `docker inspect`, `docker logs`, `docker exec`;
- Docker lifecycle operations;
- systemd lifecycle operations;
- UFW/firewall mutation;
- `nft` / `iptables` inspection;
- process/container environments;
- application configuration, logs or data;
- browser/session material;
- credentials, tokens or secret values in output.

## Evidence privacy

Persisted/output evidence contains only:

- service ID and public hostname;
- zone;
- route/listener/Docker/firewall enum classes;
- boolean connector state;
- connector edge count;
- public-safe drift reason codes;
- PASS/DRIFT/BLOCKED.

It must not contain:

- private IP addresses or subnets;
- internal ports;
- raw socket output;
- raw firewall rules;
- process/container identities;
- account/tunnel identifiers;
- Access AUD values;
- credentials, tokens, cookies or session material;
- protected application configuration, logs or data.

## Source vs runtime authority

Merging Phase 7 source proves only that the bounded audit implementation and tests are reviewed.

It does **not** authorize:

- execution against the RPi5;
- Cloudflare credential use;
- Docker/firewall/systemd inspection;
- remediation of any detected drift;
- Cloudflare/DNS/Tunnel changes;
- service/container/network changes.

A later runtime execution requires fresh owner authorization binding the exact merged SHA and the read-only metadata/credential surfaces required by this audit.

Any `DRIFT` requiring a change becomes a separate service-specific issue. Phase 7 itself never repairs, restarts, narrows, broadens or cleans up anything.

## Runtime execution boundary after #905

The merged audit core is not a secret loader. Runtime access goes through the exact-release installed Cloudflare operator:

`sudo -n /usr/local/sbin/rpi5-cloudflare phase7-ingress-drift-audit --expected-main <exact-main-sha>`

That wrapper verifies the fixed canonical checkout before reading the fixed Tunnel capability secret. It passes the API token only on stdin to `scripts/ingress_drift_audit.py`; the token is never placed in argv or environment. The child receives the account binding through a minimal environment and discovers the single expected remotely-managed `rpi5-tunnel` through GET-only Cloudflare calls.

If the canonical checkout is stale, use the separately reviewed `scripts/rpi5_main_exact_source_prepare.py` boundary. Its read-only mode performs no fetch. A later exact owner authorization may permit only fixed `git fetch --no-tags origin main` plus `git merge --ff-only <exact-main>`; no reset, rebase, clean or force path exists.

The runtime sequence remains four separate gates: source merge; exact-source/operator preparation; owner-operated hidden-TTY Tunnel secret provisioning; and fresh owner authorization for the read-only Phase 7 audit. None implies the next.

## Validation

`tests/test-ingress-drift-audit-v1.py` verifies:

- exact registry coverage;
- non-authorizing source semantics;
- GET-only Cloudflare client reuse;
- clean PASS;
- unknown Cloudflare route drift;
- route-origin drift;
- wildcard Docker publish drift, including Weather's reviewed loopback target;
- missing loopback drift;
- ADMIN break-glass missing/broadened drift;
- connector/service-health drift;
- source command allowlist;
- forbidden-output boundary.

The focused test is part of `make test` / `make validate`.

## Weather PUBLIC loopback binding remediation — #915

The owner-authorized Phase 7 audit on 2026-10-08 at
`RPi5_main@fe69b6e325fa9edec04e8963b5010f946ac4d83c` returned
`DRIFT` for the single Weather PUBLIC service while the other 12 registered
services, the Cloudflare route classification and connector health passed.
The Weather Docker publish and listener were both classified `wildcard`,
not the reviewed `loopback` target. Audit execution was read-only.

The active RPi5 SIMPLE-DEPLOY target `rozkalns-weather-public-rpi5` selects
`ops/deploy/simple-deploy-compose/rozkalns-weather-public.yml` via the
registered `compose.file` and validates its exact `compose.file_sha256`.
The host-owned Compose for `weather` must publish exactly
`127.0.0.1:${WEATHER_PORT:-9180}:8000`: preserve the host port override
and container port, but never bind to `0.0.0.0`, `::`, or all interfaces.
Other service profiles, the protected private-home `env_file` reference,
persistent `weather_data`, readiness/health, and the immutable image-digest
override remain unchanged. The legacy `rozkalns-weather-public-v1.yml`
is not the active registered target and remains historical.

The Weather consumer's separate `rozkalns_weather/deploy/docker-compose.public.yml`
also uses a wildcard short port mapping. Its separate repository source
must be aligned to the same loopback-only mapping under its own explicit
source/merge authorization; changing `RPi5_main` does not change that
consumer checkout or grant cross-repository permissions.

**Source and LIVE gates remain distinct.** Neither the RPi5 source PR nor
any consumer PR changes the running container. A later, separately
authorized Weather-only rollout must first verify the current deployed
target, image digest/consumer release, clean exact host source, registry
install state, persistence protection and rollback/recovery decision.
Only an expressly scoped Weather Compose replacement may then be
considered. Its post-verification must check liveness and readiness,
Cloudflare anonymous public path and shared connector health, and repeat
the sanitized Phase 7 drift audit. A source merge must not be called
production remediation; `DRIFT` stays open until fresh runtime PASS.
No automatic retry, rollback, cleanup or unrelated host/network mutation.
