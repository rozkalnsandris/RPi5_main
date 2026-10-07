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
- wildcard Docker publish drift;
- missing loopback drift;
- ADMIN break-glass missing/broadened drift;
- connector/service-health drift;
- source command allowlist;
- forbidden-output boundary.

The focused test is part of `make test` / `make validate`.