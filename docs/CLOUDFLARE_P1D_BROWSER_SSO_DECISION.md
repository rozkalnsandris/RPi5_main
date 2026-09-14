# Cloudflare P1D browser SSO decision — issue #179

Status: **CURRENT SOURCE DECISION / P1D-04 WRITER + GITHUB DELIVERY + PRE-LIVE PREP DEFINED / NO PRODUCTION WRITE AUTHORIZED**
Decision date: 2026-09-13
Machine contract: `ops/contracts/cloudflare-p1d-browser-sso.json`

## Decision

The selected owner-phone convenience model is standard Cloudflare Access browser SSO with exact owner identity. A persistent Cloudflare One Agent/VPN connection is **not required**. Device posture is not part of the current owner-phone Access policy.

The target global Access session duration is `720h` (30 days / one month). Existing shorter application and policy session durations remain unchanged. Cloudflare documents that when an application token expires while the global token is still valid, Access re-checks the stored identity against the application's policy and can issue a new application token without another IdP login.

This preserves per-application authorization while reducing repeated password/IdP prompts. It does not create a never-expiring session.

## Security invariants

- ADMIN access keeps exact owner identity.
- No persistent `BYPASS`, `Everyone`, IP, MAC, broad email-domain, or human service-token shortcut.
- Application and policy session durations are not lengthened merely for convenience.
- Clearing cookies, private browsing, explicit logout, session revocation, IdP changes, or global-session expiry may require authentication again.
- Existing One Client enrollment may remain during the browser canary, but it is not an authorization prerequisite.

A Wi-Fi MAC is not a usable Cloudflare Access identity across Internet/cellular paths and Android MAC randomization makes it unsuitable as the canonical owner-device binding.

## Source basis

Cloudflare's current session-management documentation distinguishes the global session token from per-application tokens. The global token is stored at the team domain and provides SSO across Access applications. The documented global-session range is 15 minutes to one month.

Cloudflare documents the global session default as `24h`. The organization API models `session_duration` as optional, so an omitted field is interpreted by the source-controlled preflight and pre-LIVE preparation as the documented effective default `24h`; a present but invalid value remains fail-closed.

Cloudflare also documents that the global token cannot directly access an application; an application token is still required and Access re-evaluates policy before refreshing it. This is why a longer global session is preferred over extending every application token.

## GET-only preflight

`ops/bin/cloudflare-owner-browser-sso-preflight` is the source operator for `p1d-03-browser-sso-preflight`. It has no HTTP write primitive and reads only token validity, the Access organization, applications, and application policies.

The preflight must prove the current global session duration and the exact Dashboard owner-only policy shape without emitting owner identity, account/team/auth-domain identifiers, app/policy/AUD identifiers, cookies, JWTs, or tokens.

## P1D-04 organization-session writer

`ops/bin/cloudflare-owner-browser-sso-session-update` is the source-controlled writer for `p1d-04-global-browser-sso-session`. Source presence does **not** authorize execution.

The writer is deliberately narrow:

- exactly one fixed `PUT /accounts/{account_id}/access/organizations` primitive;
- no generic URL, method, command, path, or payload authority;
- the payload is built only from the current Organization fields admitted by Cloudflare's documented update schema;
- `session_duration=720h` is the only allowed semantic difference;
- documented response-only `created_at` / `updated_at` and the observed server-managed fields `cache_device_posture`, `has_migrated_private_apps`, and `trusted_accounts` are never copied into the PUT payload;
- those response-only fields are bound separately and must remain unchanged across the future authorized write;
- any previously unclassified top-level Organization field blocks before mutation so a schema expansion cannot silently gain write authority;
- after a successful PUT, a fresh GET must prove an explicit `720h` session, the exact intended writable projection, and unchanged response-only binding;
- one forward request maximum; no retry and no automatic rollback;
- full Organization preimage remains private and is never emitted in the sanitized report.

Before LIVE, a bounded rollback must be separately predeclared from the fresh private preimage/effective pre-write session. Source code itself does not authorize or automatically execute that rollback.

The observed `cache_device_posture`, `has_migrated_private_apps`, and `trusted_accounts` keys are treated as response/server-managed state because they were present in the fresh GET that stopped the earlier provisional writer, but they are not admitted by the current official Organization update body schema.

## No-RDC GitHub delivery path

The source-only GitHub Actions delivery path allows a future P1D-04 execution without Lenovo, RDC, or an RPi5 checkout. The LIVE workflow is `.github/workflows/cloudflare-p1d04-browser-sso-session.yml` and remains non-authorizing until exact-main CI is green, the required secrets are provisioned under separate credential authority, readiness gates pass, and the owner issues a fresh exact LIVE command.

The delivery path is capability-specific and fail-closed:

- trigger is only an `issue_comment` `created` event on issue #179;
- the LIVE workflow dispatch filter is narrowed to `/rpi5-p1d04 apply ` so the new pre-LIVE command cannot accidentally enter the writer authorization job;
- the comment author and event sender must be the exact repository owner identity, type `User`, with `OWNER` association, and the comment must not be GitHub-App-authored;
- the exact LIVE command shape is `/rpi5-p1d04 apply HEAD=<exact-main-sha> CANARY=p1d-04-global-browser-sso-session`;
- the command SHA must equal the default-branch event SHA, and the operator checkout is pinned to that exact SHA with persisted Git credentials disabled;
- workflow reruns are rejected; a new attempt requires a new owner comment and therefore a new owner decision;
- immediately before any Cloudflare request, the Actions adapter re-reads current `main` and requires the exact-SHA push runs for `Validate`, `FAST-LANE policy drift`, and `GITHUB-ONLY policy drift` to be completed successfully;
- GitHub workflow permissions are read-only (`contents: read`, `actions: read`) and the workflow posts no automatic result comment;
- Cloudflare account/read/write credentials are supplied only through dedicated GitHub Actions secrets named by the machine contract; source does not create, modify, expose, or authorize those secrets;
- legacy Cloudflare token environment names and custom API-base overrides are rejected;
- read and write tokens must differ and both must verify active before either readiness preparation or the writer can proceed;
- the LIVE Actions adapter delegates to the same fixed writer, preserving one forward PUT maximum, no retry, no automatic rollback, private preimage handling, response-only binding, and sanitized output.

Credential provisioning is a separate state change. Source readiness does not imply LIVE readiness.

## No-RDC P1D-04 pre-LIVE preparation

Issue #529 adds `.github/workflows/cloudflare-p1d04-prelive-prep.yml`, a separate capability-specific **GET-only** preparation path. It closes the no-RDC readiness gap without granting Cloudflare write authority.

The exact owner command is `/rpi5-p1d04 prep HEAD=<exact-main-sha> CANARY=p1d-04-prelive-prep`. It is bound to issue #179, the exact owner User identity, the exact current main SHA, run attempt 1, and positively green exact-main `Validate`, `FAST-LANE policy drift`, and `GITHUB-ONLY policy drift` runs. Source merge does not authorize this workflow execution; it requires a fresh separate owner authorization.

The prep path consumes only the dedicated P1D-04 account/read/write secret names already defined by the contract. It verifies that the read/write token values differ and verifies both tokens as active with `GET /user/tokens/verify`. It then uses only the read token for one fresh `GET /accounts/{account_id}/access/organizations`.

The prep logic reuses the existing writer's Organization schema/projection and intended `session_duration -> 720h` plan construction, but it never imports or invokes the Organization write client. Unknown top-level Organization fields, an already-target `720h` session, an invalid explicit duration, SHA/CI/token mismatch, or privacy invariant failure block before any future LIVE mutation.

The full Organization preimage and intended update payload remain private in runner memory. Public output contains only a deterministic `sha256:` fingerprint of canonical JSON, field counts, effective/current session evidence, target session, and the single intended semantic diff. Account ID, auth domain, team name, tokens, full preimage, intended payload, and response-only values are never emitted.

The sanitized result also predeclares a bounded inverse recovery descriptor. Its target is the fresh effective pre-write session. When `session_duration` is omitted, the inverse target is explicitly `24h`, matching the documented default. Rollback is never automatic: any rollback write requires a fresh Organization GET and a separate owner authorization.

The prep path contains no Cloudflare `POST`, `PUT`, `PATCH`, or `DELETE` primitive and no generic execution authority.

## Future live sequence

1. Merge the P1D-04 pre-LIVE prep source and obtain positively green exact-main push CI.
2. Run `p1d-03-browser-sso-preflight` GET-only again from exact merged source and prove the global session is still not `720h`.
3. Confirm the dedicated P1D-04 credential names are provisioned under separate credential authority; do not broaden Cloudflare permissions or create generic execution authority.
4. Under a fresh owner authorization, run `/rpi5-p1d04 prep HEAD=<exact-main-sha> CANARY=p1d-04-prelive-prep`. Require PASS with a private-preimage fingerprint, exact schema/session evidence, and the predeclared bounded rollback descriptor.
5. Revalidate exact `main`, exact-main CI, credential readiness, and the prep evidence. No prep or source merge authorizes LIVE.
6. Request a fresh exact LIVE authorization bound to current `main` and `p1d-04-global-browser-sso-session`. The resulting `/rpi5-p1d04 apply ...` owner comment is the one-shot LIVE trigger.
7. The LIVE workflow must stop before mutation on any owner/issue/SHA/CI/secret/schema mismatch. If the Organization PUT is attempted, that LIVE authorization is consumed; any later error means STOP with no retry or automatic rollback.
8. On PASS, require the writer's fresh post-write Organization GET proof to show explicit `720h`, unchanged admitted writable projection apart from the intended session change, and unchanged response-only binding.
9. Run the A55 normal-browser canary: authenticate once, open Dashboard, then open a second protected application without a new IdP prompt. A cookie-free/incognito context must still be intercepted.
10. Only after acceptance may One Agent disable/uninstall and device-registration cleanup be considered, under a separate LIVE authorization.

No source merge authorizes Cloudflare, credential, device, DNS, Tunnel, Worker, GitHub secret, or RPi5 runtime mutation.

## References

- https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/
- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/methods/update/
