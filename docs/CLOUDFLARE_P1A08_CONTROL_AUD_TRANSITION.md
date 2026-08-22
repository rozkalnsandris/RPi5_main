# P1A-08 Control root — AUD-preserving transition override

Status: **PLAN ONLY / NO PRODUCTION WRITE AUTHORIZED**  
Canonical blocker: #199  
Base P1 contract: `ops/contracts/cloudflare-p1-exact-write-plan.json`  
Machine-readable override: `ops/contracts/cloudflare-p1a08-control-aud-preserving-override.json`

## Decision

Do not create a new exact `control.rozkalns.net` Access application during P1A.

The Control Worker currently validates Access JWTs against the audience of the existing parent wildcard application. Cloudflare documents that each Access application has a unique AUD and that an application's AUD does not change unless the application is deleted or recreated. Creating a new exact Control application would therefore introduce a different AUD before the Worker is prepared for it.

The smaller transition is to defer Control root hardening until the existing P1C wildcard-retirement gate. At that point, after every other private root is exact/protected and Deals cleanup is complete, update the existing parent wildcard application **in place**:

`*.rozkalns.net` → `control.rozkalns.net`

The same PUT also reshapes that same application to the intended Control owner policy: 24h session, exactly one owner-email Allow at precedence 1, empty Require/Exclude, no Bypass/Everyone/service-token human path.

Because the application is updated rather than deleted/recreated, the private application ID and AUD must remain unchanged. This preserves the Control Worker's current audience binding without a Worker source/config/deploy transition.

## Why the retarget is deferred to P1C

Retargeting the wildcard during P1A would remove the current catch-all Access safety net before the existing P1B origin-protection and Deals gates are complete. The base plan intentionally retires the wildcard only after:

- Kuma/Grafana/Prometheus/AdGuard/Hermes/Portainer/Home Assistant exact apps are accepted;
- all required Tunnel Protect-with-Access canaries pass;
- Dashboard exact/protected state remains accepted;
- Deals IP Bypass is removed and family/service-token access remains proven;
- Deals Protect-with-Access passes;
- no unclassified Access hostname or Tunnel route exists;
- the temporary exact public Tech carve-out is still present.

The AUD-preserving retarget therefore replaces the old P1C wildcard DELETE, not the earlier P1A-08 create.

## Cloudflare API facts used

Current Cloudflare documentation provides:

- Access application update: `PUT /accounts/{account_id}/access/apps/{app_id}` with `Access: Apps and Policies Write`;
- a self-hosted application update accepts the application domain and policy configuration;
- each Access application has an application AUD;
- the AUD does not change unless the application is deleted or recreated;
- overlapping Access paths continue to use the more-specific application, preserving the dedicated Control webhook path application.

These facts must be rechecked immediately before any future live gate because external platform contracts can change.

## Authorization consequence

The owner authorization previously supplied for:

`p1a-08-control-root-exact-app`

was for one **POST create** plus only its attributable rollback. The reviewed strategy now changes the live operation materially to a later **PUT update of the existing parent application**.

Therefore the old authorization is **retired without consumption**:

- forward attempt started: false;
- Cloudflare write executed: false;
- rollback executed: false;
- it must never be reinterpreted as authorization for the new PUT.

A future live retarget requires a new exact owner authorization after all P1C-03 preconditions are freshly proven.

## Future P1C-03 forward gate

Immediately before the future PUT, fail closed unless fresh GET-only evidence proves all of the following:

1. current source and exact-main CI are the reviewed baseline;
2. all private admin roots except Control are exact/no-Bypass;
3. all required P1B Tunnel Protect-with-Access canaries pass;
4. Deals no-BYPASS + family/service-token + Protect state passes;
5. Dashboard exact/protected state passes;
6. Control root still resolves to the current parent wildcard application;
7. the Worker's expected audience equals that parent application's current AUD, compared privately;
8. the more-specific Control webhook application is present and unchanged;
9. Tech's temporary public exact Bypass remains present;
10. `rozkalns.net` remains public;
11. no unclassified Access hostname or Tunnel route exists;
12. the complete parent application and its policies are captured privately with mode 0600;
13. owner email is supplied privately and is never logged.

## Allowed forward diff

Exactly one Access application is updated. No other Access/Tunnel/DNS/Worker object may change.

Allowed semantic changes to that same application:

- domain: `*.rozkalns.net` → `control.rozkalns.net`;
- name → `RPi5 Control Owner`;
- session duration → `24h`;
- policies → exactly one owner-email Allow, precedence 1, empty Require/Exclude.

The application identity and AUD must remain unchanged. No DELETE/recreate is allowed.

## Required postconditions

Fresh read-only evidence must prove:

- same private application ID;
- same private application AUD;
- wildcard domain absent;
- Control root resolves exact to the retargeted application;
- owner-only policy shape and 24h session;
- owner browser PASS;
- unauthenticated denial PASS;
- Control Worker JWT validation PASS;
- webhook path still resolves to its unchanged more-specific application and runtime behavior remains healthy;
- all other private roots remain exact/protected;
- Deals family/service-token behavior remains PASS;
- Tech and apex remain public;
- no unclassified hostname/route appears.

Any failed/ambiguous postcondition triggers only the predeclared rollback path.

## Rollback

Rollback is a PUT of the exact captured parent-application/policy preimage back to the **same application ID**, followed by fresh GET verification that:

- wildcard semantics are restored;
- the original AUD is still unchanged;
- Control returns to the previous wildcard resolution;
- webhook and all unrelated applications remain unchanged.

No blind retry is allowed after a forward attempt. Authorization is consumed when the first forward PUT starts regardless of HTTP result.

## Tech cleanup

The existing `p1c-04-remove-tech-public-carveout` remains after this gate, but its prerequisite becomes:

`p1c-03-control-root-retarget PASS` and parent wildcard domain absent.

Only then may the temporary exact public Tech application be removed under its own separate authorization.

## Current safe next step

Merge/review of this source-only override does not authorize any production mutation. After merge, P1A-08 is treated as **deferred/no-write**, and execution proceeds to P1B-01 readiness rather than attempting a Control Access write.
