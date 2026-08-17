# Cloudflare owner-phone access contract

Status: **design contract / no production mutation**  
Canonical audit: `docs/CLOUDFLARE_ZERO_TRUST_MOBILE_AUDIT_2026-08-17.md`  
Tracking issue: #177

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

1. Install Cloudflare One Agent on the Android phone.
2. Enroll it into the Zero Trust organization using an owner-only device-enrollment policy.
3. Keep Cloudflare One Client connected/auto-connected.
4. Require exact owner identity for ADMIN Access applications.
5. Add the Cloudflare One Client `Require WARP` posture check to the ADMIN owner policy after a canary passes.
6. Optionally add a minimum supported Android OS-version posture check.
7. Verify the same policy on:
   - home Wi-Fi;
   - cellular data;
   - a non-enrolled browser/device, which must be denied.

## Identity-provider hardening

The fresh 2026-08-17 inventory shows both Cloudflare and One-Time PIN login methods are available in the Zero Trust organization.

For **ADMIN** applications, prefer the Cloudflare identity provider restricted to the Cloudflare account/member identity when the owner account is protected with strong MFA. Cloudflare's 2026 Access documentation describes its own IdP as backed by Cloudflare account security, including MFA, and identifies it as a stronger default than email One-Time PIN for most use cases.

Target separation:

- ADMIN: Cloudflare IdP / exact owner identity; do not rely on email OTP as the normal owner login path;
- FAMILY_PRIVATE: keep a deliberately separate family authentication policy/login method if family sharing requires it;
- PUBLIC: no Access authentication.

For the highest-impact ADMIN applications, independently evaluate Cloudflare Access independent MFA as an additional layer. Do not enable it blindly: first verify its session behavior on the owner phone so MFA hardening does not create unnecessary prompts on every normal visit.

## Session model

### Preferred convenience path

Cloudflare documents **Authenticate with Cloudflare One Client** for Access applications under its client-session feature. As of the 2026-06-04 Cloudflare documentation this feature is explicitly presented as **Beta**.

If the account exposes the feature and a canary passes:

- enable it only for the intended ADMIN applications first;
- use a bounded owner-phone client session, initially targeting 30 days if accepted by the owner;
- rely on the enrolled device identity while the client session is valid;
- require reauthentication when that session expires or is revoked.

Cloudflare states that when this mode is enabled, the Cloudflare One Client session duration takes precedence over the normal Access application/policy/global durations. A valid client session can therefore avoid repeated IdP prompts while the enrolled client is running.

### Stable fallback if the Beta path is unavailable or unsuitable

Keep standard Cloudflare Access SSO:

- use an exact/narrow ADMIN Access app/policy;
- set the global Access session to a bounded duration, with one month being Cloudflare's documented maximum;
- keep application/policy tokens shorter if desired;
- let Cloudflare automatically issue a new application token while the global token remains valid and policy checks continue to pass.

This fallback still prevents a login prompt for every ADMIN hostname. The owner authenticates periodically rather than per service.

`Require WARP` device posture can remain part of the authorization policy even when the Beta client-session authentication path is not used.

## Why not Device UUID initially

Cloudflare supports Android Device UUID posture, but its documentation states that the UUID must be assigned through managed deployment/MDM and cannot be assigned manually. The initial personal-phone posture therefore uses:

- exact owner identity;
- `Require WARP`;
- optional supported OS-version posture.

Device UUID can be reconsidered if the phone later becomes MDM-managed.

## Lost-phone / compromise response

The convenience session is acceptable only while it is revocable. The recovery contract must include:

1. revoke the affected Cloudflare One device/user session;
2. disable or remove the device's ability to satisfy the ADMIN access policy;
3. verify ADMIN access fails from the lost/revoked device context;
4. re-enroll a replacement device through the owner-only enrollment path;
5. never restore convenience by adding a broad source-IP Bypass.

No exact identity, device ID, token, account ID, or recovery secret belongs in Git.

## Production activation gate

No setting in this document is authorized for production by the document itself.

Before any Access write:

1. fresh GET-only Access/device/posture inventory;
2. exact desired policy diff;
3. rollback plan;
4. explicit owner authorization for the exact mutation;
5. bounded write;
6. Wi-Fi proof;
7. cellular proof;
8. non-enrolled denial proof;
9. public-site regression proof;
10. rollback on any failed invariant.

## Primary Cloudflare references

- Client sessions / Authenticate with Cloudflare One Client: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/
- Session management: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- Authorization cookie / global SSO token: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/
- Cloudflare as identity provider: https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/cloudflare/
- Independent MFA: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/independent-mfa/
- Manual Android enrollment: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/manual-deployment/
- Device enrollment permissions: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/device-enrollment/
- Client posture checks: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/
- Device UUID requirements: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/device-uuid/
