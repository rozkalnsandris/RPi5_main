# Cloudflare P1D client-session compatibility — issue #179

Status: **SOURCE / PLAN ONLY / NO CLOUDFLARE MUTATION AUTHORIZED**  
Source revalidation: 2026-08-25  
Extends: `ops/contracts/cloudflare-p1d-owner-phone-posture.json#client_session_beta`

## Purpose

The owner-phone P1D design keeps `Authenticate with Cloudflare One Client` as a later, separate Access Beta convenience canary. This follow-up pins the compatibility conditions that must be proven before that canary is even eligible for an owner authorization.

It does not change the selected ADMIN posture: exact owner identity plus `Require Gateway` remains the security control. Client-session authentication is only a bounded convenience layer intended to reduce repeated IdP prompts on an already-enrolled owner phone.

## 2026-08-25 Cloudflare documentation revalidation

Current official Cloudflare documentation states:

- `Authenticate with Cloudflare One Client` is supported only for Access applications protected by **Allow or Block** policies;
- the feature uses the identity from the IdP that enrolled the Cloudflare One Client and avoids repeated IdP authentication while the bounded client session remains valid;
- only one user can be registered on a device at a time for this client-session flow;
- the Cloudflare Access team domain and the IdP authentication path must remain reachable through the Cloudflare One Client;
- **Binding Cookie is not supported**: an Access application with Binding Cookie enabled cannot use `Authenticate with Cloudflare One Client`;
- Cloudflare's Access application API exposes both `allow_authenticate_via_warp` and `enable_binding_cookie`, so the incompatibility can be checked GET-only before any later write;
- app-level `allow_authenticate_via_warp` overrides the organization default and is writable through the existing Access application update surface.

Official references:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/methods/get/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/methods/update/

## Binding Cookie security boundary

Binding Cookie is an independent Access security setting. Disabling it changes the application's cookie theft/replay protection semantics.

Therefore the first client-session Beta canary must **not** bundle a Binding Cookie change.

If a fresh GET-only target-application read returns `enable_binding_cookie=true`:

1. STOP before any client-session write;
2. do not silently disable Binding Cookie;
3. do not consume a future client-session authorization on an incompatible target;
4. require a separate source/security decision and separate owner authorization for any Binding Cookie change;
5. after that separate change, re-run the GET-only compatibility preflight before reconsidering the Beta canary.

If `enable_binding_cookie=false`, no Binding Cookie mutation is needed or allowed in the first Beta canary.

## Future GET-only compatibility preflight

Before a client-session Beta write for one ADMIN application, fresh exact-current evidence must prove:

- the target resolves unambiguously to the intended exact Access application;
- the target's current policy actions are compatible with Cloudflare's documented client-session constraint (`allow` or `block` only);
- `enable_binding_cookie=false`;
- the current application-level `allow_authenticate_via_warp` value is known;
- the current organization default and client-session duration are known;
- the owner phone is already enrolled and the accepted `Require Gateway` canary for the target trust path is complete;
- the team-domain and IdP path are reachable through the client;
- no private application ID, AUD, owner identity, account identifier, session token, cookie or device identifier is emitted to GitHub evidence.

A compatibility PASS is still read-only evidence. It does not authorize the later Access application update.

## First Beta canary shape — not authorized

The first future state-changing convenience canary is intentionally narrow:

- one exact ADMIN Access application only;
- app-specific `Authenticate with Cloudflare One Client` enablement only;
- no `Apply to all Access applications` bulk change;
- no session-duration change in the same canary;
- no Access policy selector/action change;
- no `Require Gateway` change;
- no Binding Cookie change;
- no IdP/login-method change;
- no Tunnel, DNS, Worker, RPi5 host or device-enrollment change.

The exact application update must preserve a private full preimage and prove after the write that the only accepted semantic change is the target application's client-session authentication flag. Rollback, if predeclared and required, restores that exact private preimage. An HTTP error, unexpected diff, ambiguous target, or failed Wi-Fi/cellular/access verification is STOP with no blind retry.

## UX expectation

This is **near-passwordless**, not permanent authentication. Cloudflare still enforces a bounded client-session lifetime. When reauthentication is required, an existing browser session at the IdP may reduce friction, but the session remains revocable and expiring.

The security objective remains: exact owner identity + organization-enrolled Gateway posture. The Beta feature only reduces repeated authentication prompts after those controls are already proven.
