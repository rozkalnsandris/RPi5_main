# Cloudflare P1 exact write plan — issue #179

Status: **PLAN ONLY / NO PRODUCTION WRITE AUTHORIZED**  
Tracking issue: #179  
Evidence baseline: `RPi5_main/main` `36f57e1e5f8b59f05b4e0e93a236ca1c92dce927`  
Machine-readable contract: `ops/contracts/cloudflare-p1-exact-write-plan.json`

## 1. Purpose

This document converts the fresh post-#182 GET-only Cloudflare reconciliation into an exact, staged write plan. It does not execute or authorize any Cloudflare mutation.

The fresh 2026-08-18 rerun established:

- exact source baseline matched;
- token active and secret-leak check PASS;
- `P0_RC=3 / BLOCKED` is policy drift, not an API failure;
- `mutation_performed=false`;
- Tunnel healthy with four connections;
- the false Dashboard route blocker is gone;
- 20 real blockers remain;
- two owner-phone posture drift items remain.

The remaining problem is primarily policy scope: seven ADMIN roots still inherit the broad `*.rozkalns.net` Access application with an IP BYPASS, Control lacks an exact root application, Deals has an exact IP BYPASS, eight protected Tunnel routes lack proven `Protect with Access`, and `tech.rozkalns.net` retains a temporary public BYPASS carve-out while the parent wildcard exists.

## 2. Non-authorization boundary

Merging this plan does **not** authorize:

- Access application or policy creation/update/deletion;
- Tunnel configuration PUT;
- DNS writes;
- device enrollment or posture changes;
- Cloudflare One Client session changes;
- RPi5 host/firewall/systemd/Docker mutation;
- application deploy or restart.

Every future forward Cloudflare mutation requires a fresh explicit owner authorization naming the exact canary ID. One authorization permits exactly one forward mutation plus only its predeclared inverse rollback if a required invariant fails.

## 3. Cloudflare semantics used by this plan

### More-specific application paths win

Cloudflare documents that when multiple Access application rules overlap, the more-specific hostname/path takes precedence and does not inherit the less-specific rule. This is the safety basis for creating exact ADMIN roots while the broad wildcard still exists.

This also protects the Control Center webhook contract: an exact root application for `control.rozkalns.net` must not replace or mutate the more-specific `control.rozkalns.net/api/github/webhook` application. The webhook path remains a deliberate public endpoint exception.

Reference: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/

### BYPASS is evaluated before ordinary ALLOW

Cloudflare documents Access policy execution with Bypass and Service Auth evaluated before ordinary Allow/Block policies. Therefore adding a stricter ALLOW to the broad wildcard does not neutralize its IP BYPASS. The migration must move ADMIN roots to exact no-BYPASS applications before the wildcard can be retired.

References:

- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/
- https://developers.cloudflare.com/cloudflare-one/faq/policies-faq/

### Exact Access app creation can include policy shape

The Access application create API accepts self-hosted application data and a `policies` array. The planned exact-app canary is therefore one forward API mutation: create one exact self-hosted application with one inline exact-owner ALLOW policy and no BYPASS/Everyone/service-token rule.

Reference: https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/methods/create/

### Protect with Access changes Tunnel configuration

For remotely managed tunnels, Cloudflare exposes `PUT /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`. The ingress `originRequest.access` object contains `required`, `teamName`, and `audTag`; `required=true` causes cloudflared to deny traffic that has not fulfilled Access authorization and validates `Cf-Access-Jwt-Assertion` before proxying L7 traffic.

Because this endpoint writes the Tunnel configuration object, every Protect-with-Access canary must capture the complete private preimage locally, canonical-hash it, permit a diff only in the target ingress `originRequest.access`, and immediately rollback the exact preimage if any unrelated ingress field changes.

References:

- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/
- https://developers.cloudflare.com/tunnel/advanced/origin-parameters/

## 4. Credential separation

Do not reuse one broad write token across the entire migration.

### Access-phase token

Minimum intended permission:

`Access: Apps and Policies Write`

It must not carry Tunnel Write or DNS Edit solely for convenience.

### Tunnel-phase token

Minimum intended permission:

`Cloudflare Tunnel Write`

It must not carry Access Apps/Policies Write or DNS Edit solely for convenience.

### General rules

- no Global API Key;
- token input hidden;
- token never printed, persisted to Git, placed in argv, or copied to GitHub evidence;
- account ID, Tunnel ID, Access IDs, policy IDs, AUD values, team name, owner email, home IP and private preimages stay outside Git;
- local private preimages use `umask 077` / mode 0600 and are destroyed after the accepted rollback window.

## 5. Universal mutation gate

Every canary must run the same gate:

1. prove exact source SHA and exact-main CI baseline;
2. fresh GET-only inventory immediately before the mutation;
3. compare live preimage to the previous accepted post-state; STOP on any unrelated drift;
4. capture the exact private object that would be changed and a canonical hash locally;
5. show the public-safe intended diff and rollback to the owner;
6. receive explicit authorization for exactly one named canary ID;
7. perform exactly one forward mutation;
8. immediately re-read the changed object and the broader Access/Tunnel inventory;
9. prove all target and unrelated-object postconditions;
10. independently test owner access, unauthenticated denial, required public regressions and service health;
11. if any required check fails, apply only the predeclared inverse rollback and re-read again;
12. STOP before the next canary. A successful canary never authorizes the next one.

No concurrent Cloudflare mutations are allowed during a canary.

## 6. P1A — exact ADMIN Access applications

Initial exact app template:

- type: `self_hosted`;
- exact hostname only;
- application session duration: `24h`;
- exactly one inline `allow` policy at precedence 1;
- Include: exactly one owner email supplied privately at execution;
- Require: none during this initial policy-scope migration;
- Exclude: none;
- no `bypass`;
- no `everyone`;
- no IP selector;
- no email-domain selector;
- no service token for human ADMIN access.

The 24h application session is deliberately bounded and substantially shorter than the observed 730h wildcard. Owner-phone convenience/posture is a later gate and must not be mixed into the policy-scope migration.

### Exact canary order

1. `p1a-01-kuma-exact-app` → `kuma.rozkalns.net`
2. `p1a-02-grafana-exact-app` → `grafana.rozkalns.net`
3. `p1a-03-prometheus-exact-app` → `prometheus.rozkalns.net`
4. `p1a-04-adguard-exact-app` → `adguard.rozkalns.net`
5. `p1a-05-hermes-exact-app` → `hermes.rozkalns.net`
6. `p1a-06-portainer-exact-app` → `portainer.rozkalns.net`
7. `p1a-07-ha-exact-app` → `ha.rozkalns.net`
8. `p1a-08-control-root-exact-app` → `control.rozkalns.net`

The order starts with lower operational-impact observability/admin surfaces and moves toward higher-impact mutation/control surfaces.

For each canary, post-state must prove:

- Access resolution is exact, not wildcard;
- selected domain is exactly the target hostname;
- exactly one email ALLOW selector;
- no Bypass/Everyone/non-identity human path;
- session duration `24h`;
- owner browser access succeeds;
- an unauthenticated/non-owner request is denied;
- `rozkalns.net` and `tech.rozkalns.net` public checks remain unchanged;
- all unrelated Access applications/policies are unchanged.

Rollback is deletion of only the newly created exact application, followed by proof that the previous wildcard resolution is restored. That rollback restores the known pre-P1 state; it is not accepted as the final security state.

### Control Center special invariant

For `p1a-08-control-root-exact-app`:

- the existing `control.rozkalns.net/api/github/webhook` application must exist before the write;
- it must remain byte-for-semantics unchanged after the write;
- the root must resolve to the new exact owner-only app;
- the webhook path must still resolve to the more-specific path application;
- Control Center Worker Access JWT verification must remain healthy.

Do not remove the webhook path BYPASS as part of root hardening. Cloudflare explicitly documents path-specific Bypass as a valid pattern for intentionally public webhook/callback endpoints.

Reference: https://developers.cloudflare.com/cloudflare-one/traffic-policies/http-policies/common-policies/ (conceptual public-endpoint pattern) and Access application path precedence reference above.

## 7. P1B — Protect with Access, one Tunnel ingress at a time

`dash.rozkalns.net` is excluded: fresh evidence already proves exact Access + loopback + `Protect with Access required=true` with one AUD and matching team.

Exact order:

1. `p1b-01-kuma-protect`
2. `p1b-02-grafana-protect`
3. `p1b-03-prometheus-protect`
4. `p1b-04-adguard-protect`
5. `p1b-05-hermes-protect`
6. `p1b-06-portainer-protect`
7. `p1b-07-ha-protect`

Preconditions for each:

- corresponding P1A exact app is proven and has no BYPASS;
- full current Tunnel config is freshly GET-read and stored privately;
- canonical hash of the complete preimage is recorded locally;
- all ingress routes still match the registry;
- exact application AUD and current team name are resolved privately;
- target route health is green before write.

The only allowed semantic diff is target `originRequest.access`:

- `required=true`;
- `teamName=<current private organization team name>`;
- `audTag=[<exact target application AUD>]`.

Everything else in the Tunnel config must be unchanged, including route count/order, services/origins, catch-all, all non-target `originRequest` fields, and all unrelated Access blocks.

Post-state must prove:

- fresh config diff is exactly the allowed target diff;
- `required=true`;
- exactly one target AUD;
- team name present and matches the organization;
- owner access succeeds;
- unauthenticated access is denied;
- origin/app health succeeds;
- unrelated ingress canonical hash is unchanged.

Rollback is an immediate PUT of the exact full preimage followed by a full GET/diff verification.

## 8. P1C — FAMILY_PRIVATE cleanup and wildcard retirement

### `p1c-01-deals-remove-ip-bypass`

Delete exactly the current Deals IP BYPASS policy only if fresh preflight proves:

- exact Deals app exists;
- exactly one IP BYPASS exists;
- two-email family ALLOW is unchanged;
- one service-token/non-identity rule is unchanged;
- both family browser and service-token canaries are ready;
- exact deleted policy preimage is captured privately.

After deletion, both family browser identities and the machine service-token path must still pass, unauthenticated access must fail, and no other Deals policy may change.

### `p1c-02-deals-protect`

Only after the Deals BYPASS is gone and family/service-token behavior is proven, enable Tunnel Protect with Access for Deals using the same full-config PUT/preimage rules as P1B.

Do not enable Protect with Access while relying on the current IP BYPASS path; the migration intentionally proves authenticated paths first.

### `p1c-03-retire-parent-wildcard`

Delete `*.rozkalns.net` only when all of these are true:

- all seven Tunnel-backed ADMIN roots resolve exact/no-BYPASS;
- Control root resolves exact/no-BYPASS and webhook path still works independently;
- Dashboard exact + Protect state remains PASS;
- every intended protected Tunnel root has Protect with Access proven;
- Deals no-BYPASS + family/service-token + Protect state is PASS;
- `tech.rozkalns.net` temporary exact public carve-out is still present;
- `rozkalns.net` remains public;
- no unclassified Access hostname or Tunnel route exists;
- complete wildcard app/policy private preimage is stored locally for rollback.

Rollback, if needed, recreates the wildcard application/policies from that local private preimage. The recreated object may receive new Cloudflare IDs; rollback acceptance is semantic equivalence, not ID equality.

### `p1c-04-remove-tech-public-carveout`

This must be **after** wildcard retirement. Removing the exact `tech.rozkalns.net` Everyone BYPASS while the wildcard still exists could cause Tech to fall back into the private wildcard and break the PUBLIC contract.

After wildcard absence is proven, delete only the temporary exact Tech Access app. Post-state must prove:

- Tech has no Access application;
- Tech is reachable unauthenticated as PUBLIC;
- `rozkalns.net` remains PUBLIC;
- all private roots remain protected.

## 9. P1D owner-phone posture — intentionally blocked pending source decision

Do not combine owner-phone posture with P1A/P1B/P1C.

The current canonical contract names `Require WARP` as the initial posture target. Fresh Cloudflare documentation now states that **Require WARP checks all versions of WARP, including the consumer version**. Cloudflare separately documents **Require Gateway** as requiring traffic from a device enrolled in the organization and filtered by that organization's Gateway configuration.

That difference matters to the intended threat model. Before any posture write, a new source-only decision must compare:

- `Require WARP` convenience and its consumer-WARP acceptance;
- `Require Gateway` stronger organization-enrollment semantics;
- exact owner identity;
- Android Wi-Fi and 4G/5G behavior;
- non-enrolled device denial;
- operational recovery.

References:

- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-warp/
- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-gateway/

`Authenticate with Cloudflare One Client` also remains a **Beta** feature in current Cloudflare documentation and must be a separate canary after posture semantics are settled. It is not part of the initial exact-app migration.

Reference: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/

## 10. Expected blocker burn-down

This is a prediction to verify with fresh GET-only evidence, not an acceptance substitute.

- Each P1A exact ADMIN app should remove that root's wildcard-BYPASS blocker.
- P1A Control should additionally remove the missing exact root / owner-selector mismatch while preserving the webhook path exception.
- Each P1B canary should remove one `protect_with_access_not_proven` blocker.
- Deals BYPASS deletion should remove its BYPASS blocker.
- Deals Protect should remove its Protect blocker.
- Wildcard deletion should not break any intended private root because exact coverage is already proven.
- Tech carve-out deletion should remove the final PUBLIC Access-app blocker.
- Owner-phone drift remains intentionally deferred until P1D source reconciliation.

After every canary, rerun the GET-only reconciler and compare the blocker set. A blocker disappearing for the wrong reason, an unexpected new blocker, or any unclassified object is STOP.

## 11. Completion gate

P1A/P1B/P1C are complete only when fresh GET-only evidence proves:

- no ADMIN persistent BYPASS;
- no private root depends on the broad wildcard;
- all intended Tunnel-backed private roots have required Protect with Access;
- both PUBLIC hostnames remain public;
- Deals family and service-token behavior remains correct;
- Dashboard remains exact + protected;
- Control root exact-owner and webhook path exception both work;
- no unclassified Access app/hostname or Tunnel route exists;
- no unrelated object changed;
- `mutation_performed` evidence is attributable only to individually authorized canaries.

P1D posture drift may remain explicitly open until its separate source decision and owner authorization.

## 12. Source-only acceptance for this PR

This PR is Ready only if:

- the machine-readable plan parses and is internally consistent;
- `mutation_authorized=false` is pinned by tests;
- one-forward-mutation-per-authorization is pinned by tests;
- exact app and Protect target sets match the current #179 evidence;
- Deals cleanup precedes Deals Protect;
- wildcard retirement precedes Tech carve-out deletion;
- Dashboard is absent from mutation targets;
- PUBLIC hosts are never included in exact-admin creation;
- P1D remains blocked from mutation;
- no production writer/executable Cloudflare mutation code is added;
- repository CI, Gitleaks and public-safety checks pass.

Merge of this source plan remains separately owner-authorized and still does not authorize Cloudflare production writes.
