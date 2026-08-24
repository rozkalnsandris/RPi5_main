# Cloudflare P1D owner-phone posture decision — issue #179

Status: **GET-ONLY PREFLIGHT SOURCE PREPARED / PLAN ONLY / NO PRODUCTION WRITE AUTHORIZED**  
Decision date: 2026-08-19  
Source revalidation: 2026-08-22  
Tracking issue: #179  
Supersedes for P1D only: the pending source-decision text in `docs/CLOUDFLARE_P1_EXACT_WRITE_PLAN.md` section 9.

## 1. Decision

For the owner's Android phone, the preferred ADMIN device posture is:

- **Include:** exact owner identity;
- **Require:** Cloudflare **Gateway** posture;
- **Do not treat `Require WARP` as sufficient enrolled-device proof**;
- no IP `BYPASS`, `Everyone`, broad email-domain selector, browser service token, or MAC binding.

`Require Gateway` is selected because current Cloudflare documentation says it only allows requests from devices enrolled in the Zero Trust organization whose traffic is filtered by that organization's Gateway configuration. Cloudflare explicitly contrasts this with `Require WARP`, which accepts any WARP instance, including the consumer version.

Gateway posture is an additional device signal. It does **not** replace the owner's authenticated identity.

## 2. Current Cloudflare source basis

Reviewed official Cloudflare documentation on 2026-08-19 and revalidated against current docs/API on 2026-08-22.

### Require Gateway versus Require WARP

Cloudflare documents:

- `Require WARP` checks all WARP versions, including consumer WARP;
- `Require Gateway` requires the Cloudflare One Client to be enrolled in the Zero Trust organization and connected through that organization's Gateway configuration;
- both checks are supported on Android/ChromeOS.

Therefore `Require Gateway` better matches the owner-phone threat model: exact human identity plus an organization-enrolled Gateway path.

References:

- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-gateway/
- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-warp/
- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/

### Require Gateway is a reusable posture resource

Current Cloudflare setup instructions require two distinct steps:

1. create/enable a reusable Cloudflare One Client **Gateway** posture check;
2. reference that enabled check from an Access policy.

The API exposes posture rules through:

`GET /accounts/{account_id}/devices/posture`

and identifies the Gateway check with posture type `gateway`.

Therefore P1D may not assume the reusable Gateway posture resource already exists. `p1d-00` must inventory it. If there is no single enabled Android-compatible Gateway check, the Access-policy canary is not ready.

References:

- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-gateway/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/posture/

### Enrollment cannot depend on posture

Cloudflare documents that device posture checks are not supported in device-enrollment policies because posture can only be evaluated after a device is enrolled.

The enrollment gate must therefore be identity-based and owner-only. A future live preflight must prove the current enrollment policy before deciding whether any enrollment-policy write is needed.

Cloudflare models device enrollment permissions as an Access application of type `warp` with Access policies and configured login methods.

References:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/device-enrollment/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/

### Android registration and device state

Current Cloudflare API separates WARP **registrations** from **physical devices**. Multiple registrations can exist for one physical device. Registration responses can include the assigned device settings profile and user binding, while the physical-device API carries device type and client-version metadata.

P1D therefore treats owner email, registration/device IDs, device names, keys, hardware identifiers and virtual IPs as private execution data. The source preflight correlates them only in memory and emits only counts/booleans/classifications.

References:

- https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/registrations/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/devices/

### Client mode must route through Gateway

For the initial owner-phone path, the applied device settings profile must use the normal Gateway-routing client mode. Current Cloudflare source examples represent Traffic and DNS mode with `service_mode_v2.mode = warp`.

Posture-only mode is not the selected initial path because it does not route device traffic through Gateway.

References:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/modes/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/policies/

### Authenticate with Cloudflare One Client remains separate Beta work

Cloudflare continues to document **Authenticate with Cloudflare One Client** under its Access client-session Beta feature. It is not required to enforce Gateway posture and is not part of the initial P1D posture canary.

Current Access application and organization API responses expose the client-session authentication setting (`allow_authenticate_via_warp`) and organization client session duration. The GET-only preflight records only the boolean/duration, never private application or organization identifiers.

When enabled for an Access application, Cloudflare documents that the Cloudflare One Client session duration takes precedence over application, policy, and global Access session durations. A valid client session therefore provides the intended near-passwordless owner-phone UX until that bounded session expires or is revoked.

No P1D posture mutation may change client-session authentication or session duration. The Beta convenience path requires its own reviewed canary and authorization.

References:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/
- https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/organizations/

## 3. Canonical GET-only preflight operator

The source operator for `p1d-00-fresh-owner-phone-preflight` is:

`ops/bin/cloudflare-owner-phone-preflight`

It is deliberately read-only. It uses the existing repository `CloudflareGetClient`, whose only API primitive is HTTP GET.

### Private execution inputs

The operator consumes, but must never emit or commit:

- `CLOUDFLARE_ACCOUNT_ID` from the private execution environment;
- the Cloudflare API token from a protected environment source or hidden TTY prompt, then via stdin to the runner;
- the exact owner email from a separate hidden TTY prompt, then via stdin to the runner.

The owner email is not accepted through argv or a dedicated environment variable.

### GET surfaces

The preflight is limited to:

- `GET /user/tokens/verify`;
- `GET /accounts/{account_id}/access/organizations`;
- `GET /accounts/{account_id}/access/apps`;
- `GET /accounts/{account_id}/access/apps/{app_id}/policies`;
- `GET /accounts/{account_id}/devices/posture`;
- `GET /accounts/{account_id}/devices/registrations?include=policy&status=active`;
- `GET /accounts/{account_id}/devices/physical-devices`;
- `GET /accounts/{account_id}/devices/policy`;
- `GET /accounts/{account_id}/devices/policies`.

No POST, PUT, PATCH or DELETE implementation exists in the operator.

### Public-safe report

The report may contain:

- organization binding present/not-present;
- enrollment application count, policy actions and selector **types**;
- whether the private owner identity exactly matches the one allowed enrollment email selector;
- active owner/Android registration counts;
- applied device-profile mode classification;
- client-version/tunnel-type presence booleans;
- enabled Android-compatible Gateway posture-check count;
- sanitized Dashboard/Control Access shape;
- organization/application client-session booleans/durations;
- next P1D gate IDs and public-safe blocker reason codes.

The report must never contain:

- owner email;
- account ID, auth domain or team name;
- device/registration IDs or device name;
- hardware ID, public key, virtual/public IP;
- Access application/policy/AUD IDs;
- posture rule ID;
- device profile ID.

## 4. Desired owner-phone policy shape

For an ADMIN Access application after a separately authorized P1D canary:

- action: `allow`;
- Include: exactly one owner identity supplied privately at execution;
- Require: the selected reusable `Gateway` posture check;
- Exclude: none unless separately justified and reviewed;
- Bypass: none;
- Everyone: none;
- source-IP selector: none;
- email-domain selector: none;
- service token: none for the human owner path.

The identity and Gateway requirements are conjunctive: the request must match the exact owner identity **and** pass Gateway posture.

Optional Android OS-version posture remains a later additive hardening canary. It must not be bundled into the first Gateway posture mutation.

## 5. Client-mode decision

The initial owner-phone path should use an organization-enrolled Cloudflare One Client mode that routes the phone's traffic through the organization's Gateway path.

The GET-only API preflight can prove the assigned profile configuration (`service_mode_v2.mode = warp`) for an already-enrolled device. It cannot by itself prove an end-to-end live network path. The later interactive Wi-Fi/cellular canary must prove actual Gateway connectivity before any Access-policy posture write.

Do not introduce Posture only mode as part of the first P1D canary.

## 6. Future canary sequence — not authorized

Every state-changing step below remains separately owner-authorized. This source decision authorizes none of them.

### `p1d-00-fresh-owner-phone-preflight` — GET-only

Prove, without mutation:

- exact current Zero Trust account/organization binding from private execution context;
- current device-enrollment `warp` application and policy shape;
- current login-method metadata without emitting IdP IDs;
- current owner Android registration state, if any;
- selected owner Android device-profile mode, if an unambiguous registration exists;
- current reusable Gateway posture-check inventory;
- exact Dashboard Access policy preimage in sanitized form;
- Control root resolution/preimage summary without exposing private IDs/AUD;
- current organization/application client-session authentication setting;
- no private identifier or selector value is written to Git.

The operator is diagnostic. A `PASS` means the read completed deterministically and produced a safe next-gate sequence; it does **not** mean later state-changing gates are authorized or already accepted.

### `p1d-01-owner-only-enrollment-policy` — conditional

Only if fresh preflight proves the current enrollment policy is not already owner-only.

Target shape:

- exact owner identity only;
- no broad email-domain enrollment;
- no posture selector in enrollment policy;
- no service-token enrollment path for the personal phone.

Rollback: restore the exact private enrollment-policy preimage and re-read.

### `p1d-02-owner-phone-enrollment` — interactive device state

Only after the enrollment gate is proven.

Canary requirements:

- enroll the Android phone into the intended Zero Trust organization if not already correctly enrolled;
- prove the Cloudflare One Client is connected to the organization;
- prove the applied device profile routes traffic through Gateway;
- verify both home Wi-Fi and cellular data;
- keep identifiers private;
- do not change Access application policy in the same authorization.

If an existing owner Android registration is already present, this gate still requires the Wi-Fi/cellular/Gateway canary to be positively accepted before Access policy mutation.

If the device is lost or enrollment is wrong, revoke/remove the device registration only under its own exact authorization or a predeclared revocation path.

### `p1d-02a-enable-gateway-posture-check` — conditional reusable-posture write

Cloudflare requires the reusable Gateway check to exist before it can be referenced from an Access policy.

Run this gate only if fresh `p1d-00` evidence proves there is no single enabled Android-compatible Gateway posture rule.

Allowed forward diff:

- create exactly one reusable device posture rule of type `gateway`;
- no Access application/policy change;
- no device-enrollment policy change;
- no device-profile change;
- no Gateway firewall-policy change;
- no session change.

If fresh preflight already proves exactly one suitable Gateway posture check exists, this gate is skipped with **no write**.

If multiple suitable Gateway checks exist, STOP for source/operator selection review instead of guessing which rule to bind.

### `p1d-03-dash-require-gateway`

Only after:

- owner-phone enrollment/Gateway canary is accepted;
- exactly one enabled Android-compatible Gateway posture check is established;
- fresh Dashboard policy preimage is captured privately.

Allowed semantic policy diff:

- preserve the existing exact owner Include selector;
- add exactly one `Require Gateway` device-posture condition;
- change no session duration;
- add no Bypass/Everyone/IP/email-domain/service-token selector.

Postconditions:

- owner access succeeds on Wi-Fi;
- owner access succeeds on cellular;
- non-enrolled device/browser is denied;
- exact owner on a context that does not pass Gateway is denied;
- Dashboard origin/Protect-with-Access evidence remains unchanged;
- PUBLIC regressions pass;
- all unrelated Access/device objects are unchanged.

Rollback: restore the exact private policy preimage and verify the previous policy semantics are restored.

### `p1d-04-control-require-gateway`

Only after:

- `p1c-03-control-root-retarget` has completed successfully;
- the retargeted Control root application is exact owner/no-Bypass;
- private proof confirms the same application ID and AUD were preserved by the in-place retarget;
- the more-specific GitHub webhook application remains unchanged;
- Dashboard Gateway canary is accepted.

The allowed policy diff and Wi-Fi/cellular/non-enrolled tests are the same as Dashboard. The webhook path application must not change.

Rollback: restore the exact private Control root policy preimage and prove the same application identity/AUD and the webhook application are unchanged.

### Later ADMIN expansion and convenience

Other ADMIN exact-owner applications may adopt the same Gateway requirement only after Dashboard and Control canaries are accepted. Each application remains its own explicit mutation gate; this P1D decision does not authorize bulk rollout.

A later separately reviewed Beta canary may enable `Authenticate with Cloudflare One Client` for a single ADMIN application first, with a bounded client session and no `Apply to all Access applications` bulk change. That later canary is the intended path to avoiding repeated password/IdP prompts on the enrolled owner phone.

## 7. Failure and rollback invariants

STOP and use only the applicable predeclared rollback/revocation if any state-changing canary produces:

- exact owner cannot access on Wi-Fi;
- exact owner cannot access on cellular;
- a non-enrolled device passes;
- a consumer-WARP-only/non-organization path passes as if it were the enrolled owner device;
- reusable Gateway posture state becomes ambiguous;
- any Bypass/Everyone/broad selector appears;
- session settings change unexpectedly;
- Control webhook behavior changes;
- Dashboard `Protect with Access` changes unexpectedly;
- a PUBLIC hostname becomes Access-protected;
- any unrelated Access/device object changes.

One owner authorization permits one forward production mutation or one interactive enrollment-state change, plus only its predeclared rollback/revocation if required.

## 8. Source/live completion criteria

Source readiness requires repository CI to prove:

- canonical registry selects `require_gateway`;
- owner-phone contract selects exact owner + Require Gateway;
- machine-readable P1D contract is non-authorizing;
- GET-only preflight has no write primitive and no owner-email environment/argv path;
- public report does not expose private identity/device/account/application values;
- enrollment posture is not used before enrollment;
- reusable Gateway posture resource existence is inventoried before Access-policy use;
- `Require WARP` is explicitly rejected as sufficient enrolled-device proof;
- Dashboard precedes Control for Access-policy canaries;
- Control depends on accepted `p1c-03-control-root-retarget` and preserved application ID/AUD;
- client-session Beta remains separate and is not applied in bulk.

Live `p1d-00` execution additionally requires positively green exact-current-`main` **push** CI. If the connected GitHub surface cannot positively prove that push run, the live preflight remains blocked even when PR CI was green.

Merge of this source decision/operator still does not authorize Cloudflare, phone, RPi5, DNS, Tunnel, Access, posture, session, deploy, or restart mutation.
