# Cloudflare owner-phone access contract

Status: **design contract / no production mutation**  
Canonical audit baseline: `docs/CLOUDFLARE_ZERO_TRUST_MOBILE_AUDIT_2026-08-17.md`  
P1D posture decision: `docs/CLOUDFLARE_P1D_OWNER_PHONE_POSTURE_DECISION.md`  
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

The 2026-08-19 P1D source decision supersedes the earlier `Require WARP` posture recommendation for the owner-phone ADMIN path.

1. Install Cloudflare One Agent on the Android phone.
2. Enroll it into the Zero Trust organization using an owner-only device-enrollment policy.
3. Keep Cloudflare One Client connected to the intended organization and Gateway path.
4. Require exact owner identity for ADMIN Access applications.
5. Add the Cloudflare One Client **Require Gateway** posture check after a separately authorized canary.
6. Do **not** treat `Require WARP` alone as sufficient enrolled-device proof because Cloudflare documents that it also accepts consumer WARP.
7. Optionally add a minimum supported Android OS-version posture check only in a later separate hardening canary.
8. Verify the same policy on:
   - home Wi-Fi;
   - cellular data;
   - a non-enrolled browser/device, which must be denied;
   - an owner-authenticated context that does not pass the organization Gateway posture, which must be denied.

`Require Gateway` is a device condition, not the owner identity. The intended Access policy remains exact owner identity **and** Gateway posture.

## Device-enrollment boundary

Cloudflare documents that posture checks cannot be used in device-enrollment policies because posture is evaluated only after enrollment.

Therefore:

- device enrollment must be gated by exact owner identity/login method;
- a fresh GET-only preflight must inspect the current enrollment policy before any write;
- if the current enrollment policy is already owner-only, do not mutate it;
- no broad email-domain or service-token enrollment path should be introduced for the personal phone.

## Identity-provider hardening

For **ADMIN** applications, prefer a strong owner identity/login method protected by MFA. Keep the exact identity value private and out of Git.

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

If the account exposes the feature and a later separate canary passes, it may be evaluated for selected ADMIN applications. It is not required for Gateway posture and must not be enabled in the same authorization as the initial posture mutation.

When enabled for an Access application, a valid Cloudflare One Client session is the intended near-passwordless phone experience: the user authenticates once with the client and is not prompted to re-authenticate with the IdP again while that bounded client session remains valid and the client is running. This convenience feature remains a separate authorization boundary from posture.

## Why not Device UUID initially

Cloudflare supports Android Device UUID posture, but current documentation states that the UUID must be assigned through managed deployment/MDM and cannot be assigned manually.

The initial personal-phone posture therefore uses:

- exact owner identity;
- `Require Gateway`.

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

No exact identity, device ID, token, account ID, policy ID, AUD value, team name, or recovery secret belongs in Git.

## P1D canary order

The source-only decision fixes this future order:

1. GET-only owner-phone/device/enrollment/posture preflight;
2. conditionally tighten the enrollment policy only if it is not already owner-only;
3. separately enroll the owner phone and prove organization Gateway posture on Wi-Fi + cellular;
4. Dashboard: preserve exact owner Include and add only Require Gateway;
5. Control root: only after `p1c-03-control-root-retarget` is accepted and the same application identity/AUD is privately proven preserved; preserve the more-specific GitHub webhook application unchanged;
6. only then consider other ADMIN applications one at a time.

Every state-changing step requires its own explicit owner authorization.

## Production activation gate

No setting in this document is authorized for production by the document itself.

Before any Access write:

1. exact source/contract baseline;
2. fresh GET-only Access/device/posture inventory;
3. exact desired policy diff;
4. private full policy preimage and rollback plan;
5. explicit owner authorization for the exact mutation;
6. one bounded write;
7. fresh API re-read;
8. Wi-Fi proof;
9. cellular proof;
10. non-enrolled denial proof;
11. non-Gateway owner-context denial proof;
12. public-site regression proof;
13. rollback on any failed invariant.

Device enrollment itself is also a state change and must have its own explicit authorization.

## Primary Cloudflare references

- Require Gateway: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-gateway/
- Require WARP: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/require-warp/
- Client posture checks / Android support: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/
- Device enrollment permissions: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/device-enrollment/
- Manual Android enrollment: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/manual-deployment/
- Client sessions / Authenticate with Cloudflare One Client Beta: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/
- Session management: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- Device UUID requirements: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/device-uuid/
- Hardware-backed registration: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/mdm-deployment/hardware-backed-registration/
