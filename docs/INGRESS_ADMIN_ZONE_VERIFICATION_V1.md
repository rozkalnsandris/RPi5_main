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

## Route-origin Tunnel-read capability boundary

The Phase 4 route-origin audit needs two Cloudflare Tunnel GET surfaces:

- `GET /accounts/{account_id}/cfd_tunnel`;
- `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`.

Current Cloudflare API documentation lists Tunnel/Connector read permissions for both surfaces, including `Cloudflare Tunnel Read`.

Official references:

- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/methods/list/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/

The existing GitHub `P1D03` capability contract is **not reusable** for this purpose. Its reviewed GET surface is Cloudflare Access only; it does not establish Tunnel or Connector read authority. Reusing its account/token secrets for Tunnel discovery would silently widen the credential trust boundary.

Therefore `route_origin_runtime_capability.status` is currently `unbound`. While it is unbound:

- the route-origin workflow injects no Cloudflare credential secret;
- the auditor exits `BLOCKED` with only the sanitized classes `capability_requirement=tunnel-read` and `capability_binding=unbound`;
- no Cloudflare API request is attempted;
- no account ID, tunnel ID, token, private route coordinate or raw provider payload is emitted.

Changing this state to a usable Tunnel-read binding requires a **separate owner-authorized source change** that names the reviewed capability contract. Provisioning a secret or changing token permissions is an additional separate owner gate. Merely changing `status` to `bound` is insufficient: the current auditor intentionally has no credential wiring and fails closed as `not-wired` until that wiring is reviewed.

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
