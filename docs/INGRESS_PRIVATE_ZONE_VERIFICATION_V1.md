# PRIVATE zone verification contract v1

Status: **source readiness only**  
Roadmap: `RPi5_main#60` Phase 5  
Implementation: `RPi5_main#866`  
Machine contract: `ops/contracts/private-zone-verification-v1.json`

## Purpose

Phase 5 verifies the canonical PRIVATE zone independently from PUBLIC and ADMIN. The target set is derived from `ops/contracts/ingress-registry-v1.json` by `zone=PRIVATE`. At this source baseline it contains exactly one service: `hermes-deals / deals.rozkalns.net`.

The registry calls the zone/access class `PRIVATE`; the hostname policy calls its trust class `FAMILY_PRIVATE`. They are intentionally equivalent layers of the same private-user boundary and are not aliases for `ADMIN` or `PUBLIC`.

## Required source semantics

The Deals PRIVATE service must retain:

- Cloudflare Access required;
- application scope `exact-or-narrow-family`;
- no PUBLIC inheritance;
- no application scope broad enough to cover ADMIN or PUBLIC hostnames;
- no persistent or alternate public bypass;
- unauthenticated external behavior reduced to `access-challenge` or `denied`;
- authorized private-user result recorded only as `PASS`, `FAIL` or `UNKNOWN`;
- loopback route/origin;
- loopback listener;
- no direct LAN path and no LAN break-glass;
- runtime ingress owner `rozkalnsandris/RPi5_main`;
- recovery reference present.

No identity value is required to prove the source shape.

## SIMPLE remediation policy

Phase 5 verification is persistent; one-off remediation automation is not.

If a PRIVATE Access policy is found in a state that violates this contract, the default remediation path is:

1. owner reviews the exact application and policy in the Cloudflare Zero Trust dashboard;
2. owner performs the smallest manual target-only policy change under separate explicit LIVE authority;
3. the repository does not retain a purpose-built mutation workflow, credential bridge, protected snapshot engine or diagnostic control-plane for that one-time change;
4. after the manual change, the existing Phase 5 GET-only verifier, route verify, host isolation check and protected browser acceptance provide fresh evidence.

If the Cloudflare dashboard does not make the target/scope unambiguous, STOP instead of creating a generic privileged API writer.

A manual operator report is not runtime proof by itself. Phase 5 remains incomplete until the existing verifiers produce fresh PASS evidence.

## Runtime verifier surfaces

### External Access / anonymous edge

The source-defined workflow `.github/workflows/cloudflare-phase5-private-external.yml` accepts only a fresh direct-owner command on #866:

`/rpi5-p5-private-external check HEAD=<exact-main-sha> CANARY=phase5-private-external-v1`

It reuses only the existing P1D03 GET-only Access credential lane. It performs Cloudflare API GETs plus one unauthenticated HTTPS GET to the public hostname, does not follow redirects, never reads the response body, and emits only sanitized classes/booleans. Bypass policy scope is reduced to `absent`, `scoped`, `public` or `unknown`; only `absent` can PASS, a proven public/Everyone bypass FAILs, and scoped/unknown bypass remains UNKNOWN rather than being mislabeled public. The verifier also emits only sorted Bypass include-selector type names (for example `ip`, `service_token` or `everyone`) as `bypass_policy_selector_classes`; selector values are never emitted, and malformed/unsupported selector shapes add only the `unknown` class.

### Route origin

Phase 5 does **not** create a new Tunnel credential consumer. The reviewed Deals V19 operator already exists at `.github/workflows/deals-9128-route-cutover.yml` / `scripts/cloudflare_deals_route.py`.

For Phase 5 only its existing read-only `/rpi5-61 verify` -> `verify-loopback` operation is admissible. That verify path checks the Deals route plus terminal catch-all without freezing unrelated tunnel inventory; the legacy `check` and `cutover` validators remain fleet-exact. A fresh runtime gate must require `ROUTE_STATE=loopback`, Access edge protection still present, and `CONFIG_MUTATED=false`. The `check` and `cutover` operations are not authorized by Phase 5 verification authority.

### RPi5 host isolation

`scripts/phase5_private_host_isolation.py --expected-main <exact-main-sha>` requires an exact clean checkout and uses only Git identity/cleanliness checks, `ip -j -4 route get 1.1.1.1`, `ss -H -lnt`, and a connect-only probe to the locally discovered LAN address. The probe target is source-bound to the already documented Deals listener.

PASS requires a loopback-only listener and an absent LAN path. The script emits neither the discovered LAN address nor listener addresses/ports/process/container identities.

### Protected authorized-private path

`scripts/phase5_private_authorized_path_receipt.py` intentionally does not automate the browser. Under a later separate owner authorization, the owner uses the existing normal Cloudflare Access browser path and records only `PASS`, `FAIL` or `UNKNOWN` for `deals.rozkalns.net`.

The operator must not read browser profiles, cookies, session state, credentials, tokens, identity values, developer-tools exports or protected response content.

## Completion

Phase 5 may be marked COMPLETE only when separately authorized fresh evidence proves:

1. PRIVATE/FAMILY_PRIVATE Access scope PASS;
2. unauthenticated challenge/deny PASS;
3. authorized private-user path PASS;
4. no ADMIN/PUBLIC scope overlap or public bypass;
5. Tunnel route origin loopback PASS using the existing V19 verify operation;
6. host listener loopback and LAN path absent;
7. runtime owner and recovery reference PASS;
8. sanitized evidence is recorded.

Any FAIL/UNKNOWN that needs remediation becomes a separate reviewed issue and separate owner authorization.

## Source/runtime boundary

Merging this source does not execute any Cloudflare or host verifier, does not authorize the protected browser path, does not change Access/Tunnel/DNS/firewall/listeners/services, and does not prove current runtime state.
