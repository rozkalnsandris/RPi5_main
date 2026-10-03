# ADMIN zone verification contract v1

Status: **source readiness only**  
Roadmap: `RPi5_main#60` Phase 4  
Implementation: `RPi5_main#819`  
Machine contract: `ops/contracts/admin-zone-verification-v1.json`

## Purpose

Phase 4 verifies that every service classified as `ADMIN` remains behind the intended administrator trust boundary while preserving only the LAN recovery behavior explicitly allowed by the canonical ingress registry.

The ADMIN set is derived from `ops/contracts/ingress-registry-v1.json` by `zone=ADMIN`. The machine contract freezes the currently expected service IDs and public hostnames so a later registry change becomes visible drift rather than silently changing the verification target.

The current registry-derived set contains eight RPi5-hosted ADMIN services: Hermes admin, Portainer, Grafana, Home Assistant, AdGuard UI, Uptime Kuma, Prometheus and Dashboard.

Cloudflare Worker-only services are not added to this RPi5-hosted ADMIN verification scope unless the canonical ingress registry itself is deliberately extended.

## Trust-class invariants

Every ADMIN service must retain all of these source-policy invariants:

- Access is required;
- Access class is `ADMIN`, distinct from `PUBLIC` and `PRIVATE`;
- Access application scope is either `exact-owner` or deliberately `exact-or-narrow-admin`, according to the desired hostname policy;
- persistent bypass is forbidden;
- an alternate public bypass is forbidden;
- unauthenticated external behavior must be denied or challenged;
- an authorized administrator path must eventually PASS under a separately authorized protected-access verification.

The contract records only the result class of authorized-admin verification. It does not record the owner identity, authentication method, cookies, session material, Access audience value or response content.

## Registry-bound origin and break-glass policy

The expected origin class, runtime owner, LAN break-glass policy and recovery reference for every ADMIN service come from the canonical ingress registry.

LAN break-glass semantics are:

- `required` => a bounded LAN recovery path must be present;
- `allowed` => a bounded LAN recovery path may be present or absent, but any present path must remain intentional and non-public;
- `forbidden` => a direct LAN recovery path must be absent.

These classifications do not authorize changing a listener, bind, route or firewall rule.

## Access-scope verification

A later read-only verification must classify each ADMIN hostname into one of:

- `exact-owner`;
- `exact-or-narrow-admin`;
- `broader-than-admin`;
- `missing`;
- `unknown`.

Only the source-projected expected class can PASS. A broad wildcard, persistent bypass, missing Access boundary or ambiguous inheritance is drift and must not be repaired under verification authority.

## Route-origin shared Tunnel operator boundary

The Phase 4 route-origin audit is a **read-only consumer** of the durable RPi5_main Tunnel operator contract:

`ops/contracts/cloudflare-tunnel-operator-v1.json`

The shared credential is account-scoped and carries `Cloudflare One Connector: cloudflared Write` so future reviewed Tunnel operations do not require a new token per project or per action. This does not make the Phase 4 audit writable.

The Phase 4 consumer remains restricted to two GET surfaces:

- `GET /accounts/{account_id}/cfd_tunnel`;
- `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`.

Its stable GitHub secret aliases are inherited from the shared operator:

- `CLOUDFLARE_TUNNEL_ACCOUNT_ID`;
- `CLOUDFLARE_TUNNEL_API_TOKEN`.

The existing `P1D03` Access capability is explicitly non-reusable.

The shared operator contract requires every consumer to define its own source gate. Read-only consumers may only use `GET`. Write consumers require an operation-specific reviewed contract, exact target, exact main binding, mutation budget and fresh explicit owner authorization. Possession of the token alone grants no operation authority.

This source does not create or rotate the token, provision GitHub secrets, authorize a Cloudflare run or authorize any Tunnel write. Provider account ID, token, tunnel ID, raw payload and private origin coordinates remain forbidden output.

See `docs/CLOUDFLARE_TUNNEL_OPERATOR_V1.md` for the durable capability contract and rotation semantics.

## Remaining infrastructure verifier

The remaining unauthenticated/infrastructure assertions are implemented by the bounded machine contract `ops/contracts/admin-zone-remaining-infra-verifier-v1.json`.

It deliberately uses two execution surfaces because a GitHub-hosted runner cannot truthfully prove RPi5-local listener or LAN-path state.

### External component

The GitHub-hosted workflow `.github/workflows/cloudflare-phase4-admin-remaining-infra.yml` is triggered only by the exact direct-owner issue command:

`/rpi5-p4-remaining-infra-external check HEAD=<exact-main-sha> CANARY=phase4-admin-remaining-infra-external-v1`

It:

- sends unauthenticated HTTPS GET requests without cookies or Authorization headers;
- does not follow redirects and never reads response bodies;
- reduces responses only to `access-challenge`, `denied`, `public`, `network-error` or `unknown`;
- reuses the existing P1D03 Access GET-only lane only to confirm that no ADMIN bypass policy is present;
- checks the exact-main registry/runtime-owner projection and recovery-reference presence;
- emits no redirect URL, account/app/policy identifier, identity value, credential, token or private coordinate.

Only `access-challenge` or `denied` can PASS the unauthenticated assertion.

### RPi5-local component

The host verifier is `scripts/cloudflare_phase4_admin_remaining_infra_host.py`.

A later fresh owner authorization may run it read-only on the RPi5 against an exact reviewed main:

`python3 scripts/cloudflare_phase4_admin_remaining_infra_host.py --expected-main <exact-main-sha>`

The script requires an exact clean tracked checkout and uses only:

- Git read-only identity/cleanliness checks;
- `ip -j -4 route get` to discover the host's current primary LAN address in memory;
- `ss -H -lnt` without process metadata;
- TCP connect-only probes to the locally discovered LAN address.

It does not invoke Docker, systemd, UFW, nftables/iptables, journals, process environments, application config/logs/data or Cloudflare credentials. It never emits the discovered LAN address, listener addresses, ports, process/container identities or raw command output.

Listener evidence is reduced to `loopback`, `lan`, `wildcard`, `mixed`, `other`, `none` or `unknown`. LAN-path evidence is reduced to `present`, `absent` or `unknown`.

The reviewed probe targets are source-bound in the verifier contract. Seven ADMIN targets inherit their probe provenance from the completed V18 LAN-origin audit; the dashboard loopback target is bound to the reviewed `dashboard_RPi5` Phase 11C launch contract. Probe coordinates are implementation inputs only and are forbidden evidence output.

`runtime_owner_matches` means the exact-main canonical registry and ADMIN projection agree that `rozkalnsandris/RPi5_main` owns the ingress/runtime control plane. It is not a process/container identity claim.

Both external and host components must PASS before the remaining infrastructure portion is complete. Source merge does not execute either component and does not authorize protected administrator access.

## Two runtime authority gates

### A. Unauthenticated / infrastructure verification

A fresh owner authorization may permit sanitized checks for:

- Access scope class;
- unauthenticated deny/challenge class;
- route/origin class;
- listener/bind class;
- LAN-path presence/absence class;
- alternate-public-bypass boolean;
- runtime-owner match;
- recovery-reference presence.

This gate must not consume authenticated administrator identity or protected application content.

### B. Protected authorized-admin verification

A separate owner authorization is required before using an existing authenticated administrator context.

Evidence is limited to `PASS`, `FAIL`, or `UNKNOWN` for the authorized path. The evidence must not persist identity values, cookies, session material, credentials, tokens, Access audience values, response content or protected application data.

If a safe protected check cannot be completed without widening that boundary, record `UNKNOWN` and STOP.

## Protected authorized-admin verifier

The protected path is intentionally **not** automated with browser-profile, cookie, token, or credential extraction. The accepted existing mechanism is the standard Cloudflare Access browser SSO model defined by `ops/contracts/cloudflare-p1d-browser-sso.json`. The previously accepted P1D-05 browser canary proves that this browser SSO model works across more than one protected application, but it does not by itself prove all eight current ADMIN service paths required by Phase 4.

The bounded Phase 4 verifier is `ops/contracts/admin-zone-protected-authorized-verifier-v1.json` with receipt validator `scripts/phase4_admin_authorized_path_receipt.py`.

Under a **fresh separate owner authorization**, the owner uses a normal browser and the existing Access browser SSO path to visit each exact ADMIN hostname. Authentication, if required, is completed directly by the owner in the browser. The agent/operator must not read the browser profile, cookies, session state, credentials, identity values, developer-tools/network export, or protected response content.

For each hostname the owner records only one class:

- `PASS` — the intended ADMIN application is reachable through the authorized Access path;
- `FAIL` — the authorized path does not reach the intended ADMIN application;
- `UNKNOWN` — a safe determination cannot be made within the protected-data boundary.

The receipt validator accepts only `source_main_sha` plus the exact eight `service_id` / `hostname` / `authorized_admin_result` tuples derived from the ADMIN projection. Any extra input field is rejected, so identity, cookie, session, token, credential, response-content, or application-data fields cannot be admitted to canonical evidence.

All eight services must be `PASS` for the protected-authorized-admin gate to PASS. Any `FAIL` or `UNKNOWN` keeps Phase 4 incomplete. Source merge does not authorize this browser canary.

## Sanitized evidence schema

The machine contract allowlists every evidence field. Per service it permits only:

- service ID and public hostname;
- Access scope class;
- unauthenticated external class;
- authorized-admin result class;
- route/origin and listener-bind classes;
- LAN-path class;
- alternate-public-bypass boolean;
- runtime-owner-match boolean;
- recovery-reference-present boolean;
- PASS/FAIL/UNKNOWN.

Private coordinates, raw firewall rules, exact internal ports, identities, cookies, sessions, credentials, tokens, account/tunnel identifiers, Access audience values, response bodies, application config/logs/data and process environments are forbidden evidence.

## Source vs runtime boundary

Merging this source outcome:

- does not prove current Cloudflare Access application or policy state;
- does not prove current unauthenticated or authenticated ADMIN behavior;
- does not prove current route, listener, LAN recovery or firewall state;
- does not authorize Cloudflare account/API access;
- does not authorize protected administrator sessions;
- does not authorize host/runtime inspection;
- does not authorize any production mutation.

Phase 4 stays incomplete after source merge.

## Phase 4 completion

Phase 4 may be marked COMPLETE only after separately authorized runtime gates prove, for every canonical ADMIN service:

1. expected Access scope semantics;
2. unauthenticated deny/challenge;
3. authorized administrator path PASS;
4. runtime owner and origin/bind class match;
5. LAN break-glass behavior matches registry semantics;
6. no alternate public bypass;
7. recovery reference is present;
8. sanitized evidence is recorded.

Any drift requiring a write becomes a separate issue and separate owner-gated remediation. Phase 5 must not begin merely because this source contract is merged.
