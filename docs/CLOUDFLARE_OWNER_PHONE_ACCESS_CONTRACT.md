# Cloudflare owner-phone access contract

Status: **design + GET-only preflight contract / no production mutation**  
Canonical audit baseline: `docs/CLOUDFLARE_ZERO_TRUST_MOBILE_AUDIT_2026-08-17.md`  
P1D posture decision: `docs/CLOUDFLARE_P1D_OWNER_PHONE_POSTURE_DECISION.md`  
P1D read-only operator: `ops/bin/cloudflare-owner-phone-preflight`  
Tracking issues: #177, #179

## Goal

Allow the owner's Android phone to reach ADMIN applications with minimal friction on both trusted Wi-Fi and cellular networks **without replacing Zero Trust identity with network-location trust**.

The security target is near-frictionless access, not an infinite never-authenticate session. Authentication must remain revocable and must periodically expire.

## Non-goals

Do not use any of the following as the owner identity:

- Wi-Fi MAC address;
- home public source IP;
- broad Access `BYPASS`;
- browser-stored service token;
- an `Everyone` Access rule;
- a broad email-domain rule for ADMIN applications.

A MAC address is local link-layer state and does not identify the device to Cloudflare when the phone uses cellular data. Device-side MAC randomization also makes it unsuitable as the canonical identity.

## Preferred Android model

The P1D source decision selects exact owner identity plus organization Gateway posture.

1. Install Cloudflare One Agent on the Android phone.
2. Enroll it into the intended Zero Trust organization through an owner-only device-enrollment Access policy.
3. Keep Cloudflare One Client in a mode that routes traffic through the organization's Gateway path (`service_mode_v2.mode = warp` in the API representation for Traffic and DNS mode).
4. Ensure exactly one suitable enabled reusable **Gateway** device-posture check exists for Android. If none exists, creating it is its own separately authorized state change.
5. Require exact owner identity for ADMIN Access applications.
6. Add the reusable **Gateway** posture check to the ADMIN owner policy only after the enrollment/device/posture canaries pass.
7. Do **not** treat `Require WARP` alone as sufficient enrolled-device proof because Cloudflare documents that it also accepts consumer WARP.
8. Optionally add a minimum supported Android OS-version posture check only in a later separate hardening canary.
9. Verify the resulting policy on:
   - home Wi-Fi;
   - cellular data;
   - a non-enrolled browser/device, which must be denied;
   - an owner-authenticated context that does not pass the organization Gateway posture, which must be denied.

`Require Gateway` is a device condition, not the owner identity. The intended Access policy remains exact owner identity **and** Gateway posture.

## Device-enrollment boundary

Cloudflare documents that posture checks cannot be used in device-enrollment policies because posture is evaluated only after enrollment.

Therefore:

- device enrollment must be gated by exact owner identity/login method;
- a fresh GET-only preflight must inspect the current `type=warp` enrollment Access application and policies before any write;
- if the current enrollment policy is already owner-only, do not mutate it;
- no broad email-domain or service-token/non-identity enrollment path should be introduced for the personal phone.

## Reusable Gateway posture-check boundary

Cloudflare documents a two-step Require Gateway setup:

1. enable a reusable Gateway posture check;
2. reference that check from an Access policy.

The reusable posture-check resource is therefore a real Zero Trust state object. It must not be silently assumed to exist.

The GET-only P1D preflight records only the public-safe classification:

- zero suitable enabled Android Gateway checks -> conditional `p1d-02a-enable-gateway-posture-check`;
- exactly one -> reusable check ready;
- more than one -> ambiguous / STOP before any Access policy write.

No posture rule ID or private account identifier belongs in GitHub evidence.

## GET-only owner-phone preflight

`ops/bin/cloudflare-owner-phone-preflight` is the canonical source operator for `p1d-00-fresh-owner-phone-preflight`.

It is deliberately GET-only and consumes private execution inputs without emitting them:

- `CLOUDFLARE_ACCOUNT_ID` from the private execution environment;
- Cloudflare API token via hidden prompt/stdin;
- exact owner email via a separate hidden prompt/stdin.

The operator reads and sanitizes:

- token validity;
- Zero Trust organization/session defaults;
- Access applications and policies, including the `type=warp` enrollment application;
- device posture rules;
- WARP registrations;
- physical devices;
- default and custom device settings profiles;
- Dashboard and Control Access application shapes.

Public-safe output may describe counts, selector **types**, boolean matches, application hostnames, client mode class, and next gate IDs. It must not emit owner email, account/auth-domain/team identifiers, device or registration IDs/names, hardware identifiers, public keys, virtual/public IPs, Access app/policy/AUD identifiers, posture-rule IDs, or profile IDs.

A live run is allowed only after the exact current `main` push CI is positively observed as green. Absence of a visible status is not PASS.

## Owner-phone device interpretation

The preflight privately correlates active registrations belonging to the exact owner identity with physical devices.

Safe readiness conditions are:

- at most one active Android registration for the owner;
- the selected registration resolves to a device settings profile;
- that profile is configured in the Gateway-routing `warp` client mode;
- current client version and tunnel type are present as non-secret booleans.

This source/API preflight does **not** claim that a configured mode alone proves a live Gateway posture PASS. After enrollment and after a reusable Gateway check exists, the device-specific posture result must be verified read-only in Cloudflare before the Dashboard policy canary. Cloudflare's dashboard exposes current posture-check results under the device details.

## Identity-provider hardening

For **ADMIN** applications, use a strong exact owner identity/login method protected by MFA. Keep the exact identity value private and out of Git.

Target separation:

- ADMIN: exact owner identity + required Gateway posture after canary;
- FAMILY_PRIVATE: separate family authentication policy/login method where family sharing requires it;
- PUBLIC: no Access authentication.

For highest-impact ADMIN applications, independent MFA may be evaluated separately. Do not bundle MFA changes into the first Gateway posture canary.

## Session model

### Stable initial path

P1D posture enforcement must not change session settings.

Keep standard Cloudflare Access SSO while the first Gateway canaries are evaluated. Session duration remains bounded and separately managed.

### Optional convenience path — separate Beta canary

Cloudflare documents **Authenticate with Cloudflare One Client** under its Access client-session Beta feature.

If the account exposes the feature and a later separate canary passes, evaluate it for a single ADMIN application first. Do not use `Apply to all Access applications` in the first canary.

When enabled for an Access application, a valid Cloudflare One Client session is the intended near-passwordless phone experience: the user authenticates once with the client and is not prompted to re-authenticate with the IdP again while that bounded client session remains valid and the client is running.

The initial P1D posture canary must not enable this feature or change global/application/policy/client-session duration.

## Why not Device UUID initially

Cloudflare supports Android Device UUID posture, but current documentation states that UUID assignment requires managed deployment/MDM and cannot be assigned manually.

The initial personal-phone posture therefore uses:

- exact owner identity;
- organization enrollment;
- Gateway-routing client mode;
- reusable `Require Gateway`.

Device UUID can be reconsidered if the phone later becomes MDM-managed.

## Hardware-backed registration limitation

Current Cloudflare documentation lists hardware-backed registration as unavailable on Android. It is therefore not an owner-phone P1D invariant.

This increases the importance of:

- exact owner identity;
- owner-only enrollment;
- revocable device registration;
- Gateway posture;
- normal phone lock/biometric controls;
- rapid lost-device revocation.

## Lost-phone / compromise response

The convenience path is acceptable only while it is revocable. The recovery contract must include:

1. revoke/remove the affected Cloudflare One device registration/session;
2. disable the device's ability to satisfy the ADMIN policy;
3. verify ADMIN access fails from the revoked device context;
4. re-enroll a replacement device through the owner-only enrollment path;
5. never restore convenience by adding a broad source-IP Bypass.

No exact identity, device ID, token, account ID, policy ID, AUD value, team/auth-domain value, posture-rule ID, profile ID, public key, IP, or recovery secret belongs in Git.

## P1D canary order

The source-only decision fixes this future order:

1. `p1d-00-fresh-owner-phone-preflight` — GET-only inventory and classification.
2. `p1d-01-owner-only-enrollment-policy` — only if the enrollment policy is not already exact-owner-only.
3. `p1d-02-owner-phone-enrollment` — separately enroll/re-enroll the Android owner phone and prove the intended organization/profile/client mode.
4. `p1d-02a-enable-gateway-posture-check` — only if no suitable reusable Gateway posture check exists; create exactly one Gateway check and then verify its read-only device result.
5. `p1d-03-dash-require-gateway` — preserve exact owner Include and add only the accepted Gateway posture requirement.
6. `p1d-04-control-require-gateway` — only after accepted `p1c-03-control-root-retarget`, preserved app identity/AUD, and accepted Dashboard canary; preserve the more-specific GitHub webhook application unchanged.
7. Only then consider other ADMIN applications one at a time.
8. The near-passwordless `Authenticate with Cloudflare One Client` Beta canary remains separate from all posture mutations.

Every state-changing step requires its own explicit owner authorization.

## Production activation gate

No setting in this document is authorized for production by the document itself.

Before any state change:

1. exact source/contract baseline and positively green exact-main push CI;
2. fresh GET-only Access/device/posture inventory;
3. exact desired semantic diff;
4. private full preimage and rollback/revocation plan where applicable;
5. explicit owner authorization for the exact mutation;
6. one bounded forward state change;
7. fresh API/read-only re-read;
8. required Wi-Fi/cellular/posture/access canaries;
9. unrelated-public/private regression proof;
10. only the predeclared rollback/revocation if a required invariant fails.

Device enrollment, reusable posture-rule creation, Access policy changes, and client-session changes are four different mutation classes and are not interchangeable authorizations.

## Primary Cloudflare references

- Require Gateway: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-gateway/
- Require WARP: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-warp/
- Posture checks / verification: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/
- Cloudflare One Client checks / Android support: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/
- Device posture API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/posture/
- Device enrollment permissions: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/device-enrollment/
- Manual Android enrollment: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/manual-deployment/
- Registrations API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/registrations/
- Physical devices API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/devices/methods/list/
- Device settings profiles API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/policies/
- Client modes: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/modes/
- Client sessions / Authenticate with Cloudflare One Client Beta: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/
- Session management: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- Access applications API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/
- Access organization API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/organizations/
- Device UUID requirements: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/device-uuid/
- Hardware-backed registration: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/mdm-deployment/hardware-backed-registration/
