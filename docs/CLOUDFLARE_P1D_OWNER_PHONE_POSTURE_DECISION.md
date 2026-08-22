# Cloudflare P1D owner-phone posture decision — issue #179

Status: **SOURCE DECISION COMPLETE / PLAN ONLY / NO PRODUCTION WRITE AUTHORIZED**  
Decision date: 2026-08-19  
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

Reviewed current official Cloudflare documentation on 2026-08-19 and revalidated on 2026-08-22.

### Require Gateway versus Require WARP

Cloudflare documents:

- `Require WARP` checks all WARP versions, including consumer WARP;
- `Require Gateway` requires the Cloudflare One Client to be enrolled in the Zero Trust organization and connected through that organization's Gateway configuration;
- both checks are supported on Android/ChromeOS.

Therefore `Require Gateway` better matches the owner-phone threat model: exact human identity plus an organization-enrolled client path.

References:

- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-gateway/
- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-warp/
- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/

### Enrollment cannot depend on posture

Cloudflare documents that device posture checks are not supported in device-enrollment policies because posture can only be evaluated after a device is enrolled.

The enrollment gate must therefore be identity-based and owner-only. A future live preflight must prove the current enrollment policy before deciding whether any enrollment-policy write is needed.

Reference:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/device-enrollment/

### Android enrollment

Cloudflare documents manual Android enrollment through the Cloudflare One Agent: enter the organization team name, authenticate, install the VPN profile, and connect.

Reference:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/manual-deployment/

### Device UUID is not the initial personal-phone control

Cloudflare's Device UUID posture requires UUID assignment through managed deployment/MDM and states that UUIDs cannot be assigned manually. The personal Android phone is not assumed to be MDM-managed, so Device UUID remains deferred.

Reference:

- https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/device-uuid/

### Hardware-backed registration is not available on Android

Current Cloudflare documentation lists hardware-backed registration as unavailable for Android. It therefore cannot be a P1D Android invariant.

Reference:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/mdm-deployment/hardware-backed-registration/

### Authenticate with Cloudflare One Client remains separate Beta work

Cloudflare continues to document **Authenticate with Cloudflare One Client** under "Configure client sessions in Access Beta". It is not required to enforce Gateway posture and is not part of the initial P1D posture canary.

When enabled for an Access application, Cloudflare documents that the Cloudflare One Client session duration takes precedence over application, policy, and global Access session durations. A valid client session therefore provides the intended near-passwordless owner-phone UX until that bounded session expires or is revoked.

No P1D posture mutation may change client-session authentication or session duration. The Beta convenience path requires its own reviewed canary and authorization.

Reference:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/
- https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/

## 3. Desired owner-phone policy shape

For an ADMIN Access application after a separately authorized P1D canary:

- action: `allow`;
- Include: exactly one owner identity supplied privately at execution;
- Require: `Gateway`;
- Exclude: none unless separately justified and reviewed;
- Bypass: none;
- Everyone: none;
- source-IP selector: none;
- email-domain selector: none;
- service token: none for the human owner path.

The identity and Gateway requirements are conjunctive: the request must match the exact owner identity **and** pass Gateway posture.

Optional Android OS-version posture remains a later additive hardening canary. It must not be bundled into the first Gateway posture mutation.

## 4. Client-mode decision

The initial owner-phone path should use an organization-enrolled Cloudflare One Client mode that actually sends the phone's traffic through the organization's Gateway path. The production preflight must prove the effective client mode and Gateway connectivity before any Access policy write.

Do not introduce Posture only mode as part of the first P1D canary. It adds certificate/mTLS/WAF behavior and a separate operational surface that is not required for the selected Gateway posture decision.

## 5. Future canary sequence — not authorized

Every step below remains separately owner-authorized. This source decision authorizes none of them.

### `p1d-00-fresh-owner-phone-preflight` — GET-only

Prove, without mutation:

- exact current Zero Trust organization/team binding;
- current device-enrollment policy/login methods;
- current owner phone enrollment state, if any;
- effective client mode and Gateway connectivity;
- current posture-check inventory;
- exact Dashboard Access policy preimage;
- exact Control root Access policy preimage only after its P1C AUD-preserving retarget exists;
- current client-session authentication setting;
- no private identifier or selector value is written to Git.

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

- enroll the Android phone into the intended Zero Trust organization;
- prove Cloudflare One Client connected to the organization;
- prove Gateway posture becomes observable;
- verify both home Wi-Fi and cellular data;
- keep identifiers private;
- do not change Access application policy in the same authorization.

If the device is lost or enrollment is wrong, revoke/remove the device registration before proceeding.

### `p1d-03-dash-require-gateway`

Dashboard is the first Access-policy posture canary because current #179 evidence already proves its exact owner Access application and `Protect with Access` boundary.

Allowed semantic policy diff:

- preserve the existing exact owner Include selector;
- add exactly one `Require Gateway` condition;
- change no session duration;
- add no Bypass/Everyone/IP/email-domain/service-token selector.

Postconditions:

- owner access succeeds on Wi-Fi;
- owner access succeeds on cellular;
- non-enrolled device/browser is denied;
- exact owner on a context that does not pass Gateway is denied;
- Dashboard origin/Protect-with-Access evidence remains unchanged;
- PUBLIC regressions pass;
- all unrelated Access objects are unchanged.

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

### Later ADMIN expansion

Other ADMIN exact-owner applications may adopt the same Gateway requirement only after Dashboard and Control canaries are accepted. Each application remains its own explicit mutation gate; this P1D decision does not authorize bulk rollout.

## 6. Session and convenience boundary

P1D selects device posture, not session behavior.

The initial Gateway canary must not:

- enable `Authenticate with Cloudflare One Client`;
- change global Access session duration;
- change application session duration;
- change policy session duration.

Standard Access SSO remains the stable fallback. A later separately reviewed Beta canary may enable `Authenticate with Cloudflare One Client` for a single ADMIN application first, with a bounded client session and no `Apply to all Access applications` bulk change. That later canary is the intended path to avoiding repeated password/IdP prompts on the enrolled owner phone.

## 7. Failure and rollback invariants

STOP and rollback the current canary if any of these occurs:

- exact owner cannot access on Wi-Fi;
- exact owner cannot access on cellular;
- a non-enrolled device passes;
- a consumer-WARP-only/non-organization path passes as if it were the enrolled owner device;
- any Bypass/Everyone/broad selector appears;
- session settings change unexpectedly;
- Control webhook behavior changes;
- Dashboard `Protect with Access` changes unexpectedly;
- a PUBLIC hostname becomes Access-protected;
- any unrelated Access/device object changes.

One owner authorization permits one forward production mutation or one interactive enrollment-state change, plus only its predeclared rollback/revocation if required.

## 8. Source-only completion criteria

This source decision is complete when repository CI proves:

- canonical registry selects `require_gateway`;
- owner-phone contract selects exact owner + Require Gateway;
- machine-readable P1D contract is non-authorizing;
- `Require WARP` is explicitly rejected as sufficient enrolled-device proof;
- enrollment posture is not used before enrollment;
- Dashboard precedes Control for Access-policy canaries;
- Control depends on accepted `p1c-03-control-root-retarget` and preserved application ID/AUD;
- client-session Beta remains separate and is not applied in bulk;
- no production writer is added;
- no private identity, device, account, policy, AUD, token, or recovery value is committed.

Merge of this source decision still does not authorize Cloudflare, phone, RPi5, DNS, Tunnel, Access, session, deploy, or restart mutation.
