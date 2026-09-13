# Cloudflare P1D browser SSO decision — issue #179

Status: **CURRENT SOURCE DECISION / P1D-04 WRITER + GITHUB DELIVERY DEFINED / NO PRODUCTION WRITE AUTHORIZED**
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

Cloudflare documents the global session default as `24h`. The organization API models `session_duration` as optional, so an omitted field is interpreted by this preflight as the documented effective default `24h`; a present but invalid value remains fail-closed. The sanitized report records whether the effective value came from an explicit API field or the documented default.

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

Issue #517 adds a source-only GitHub Actions delivery path so a future P1D-04 execution does not depend on Lenovo, RDC, or an RPi5 checkout. The workflow is `.github/workflows/cloudflare-p1d04-browser-sso-session.yml` and remains non-authorizing until separately merged, exact-main CI is green, the required secrets are provisioned under separate credential authority, a fresh P1D-03 preflight passes, and the owner issues a fresh exact LIVE command.

The delivery path is capability-specific and fail-closed:

- trigger is only an `issue_comment` `created` event on issue #179;
- the comment author and event sender must be the exact repository owner identity, type `User`, with `OWNER` association, and the comment must not be GitHub-App-authored;
- the exact command shape is `/rpi5-p1d04 apply HEAD=<exact-main-sha> CANARY=p1d-04-global-browser-sso-session`;
- the command SHA must equal the default-branch event SHA, and the operator checkout is pinned to that exact SHA with persisted Git credentials disabled;
- workflow reruns are rejected; a new attempt requires a new owner comment and therefore a new LIVE decision;
- immediately before any Cloudflare request, the Actions adapter re-reads current `main` and requires the exact-SHA push runs for `Validate`, `FAST-LANE policy drift`, and `GITHUB-ONLY policy drift` to be completed successfully;
- GitHub workflow permissions are read-only (`contents: read`, `actions: read`) and the workflow posts no automatic result comment;
- Cloudflare account/read/write credentials are supplied only through dedicated GitHub Actions secrets named by the machine contract; source does not create, modify, expose, or authorize those secrets;
- legacy Cloudflare token environment names and custom API-base overrides are rejected;
- read and write tokens must differ and both must verify active before the writer proceeds;
- the Actions adapter delegates to the same fixed writer, preserving one forward PUT maximum, no retry, no automatic rollback, private preimage handling, response-only binding, and sanitized output.

Credential provisioning is a separate state change and is not authorized by source merge or by issue #517. Source readiness therefore does not imply LIVE readiness.

## Future live sequence

1. Merge the P1D-04 writer + GitHub delivery source and obtain positively green exact-main push CI.
2. Run `p1d-03-browser-sso-preflight` GET-only again from exact merged source and prove the global session is still not `720h`.
3. Under a separate credential authorization, provision only the dedicated GitHub Actions secret inputs required by the delivery contract; do not broaden Cloudflare permissions or create generic execution authority.
4. Freshly revalidate exact `main`, exact-main CI, credential readiness, and the private Organization preimage. Predeclare the inverse recovery, but do not execute it automatically.
5. Request a fresh exact LIVE authorization bound to current `main` and the P1D-04 canary. The resulting owner comment is the one-shot trigger for the GitHub workflow.
6. The workflow must stop before mutation on any owner/issue/SHA/CI/secret/schema mismatch. If the Organization PUT is attempted, that LIVE authorization is consumed; any later error means STOP with no retry or automatic rollback.
7. On PASS, require the writer's fresh post-write Organization GET proof to show explicit `720h`, unchanged admitted writable projection apart from the intended session change, and unchanged response-only binding.
8. Run the A55 normal-browser canary: authenticate once, open Dashboard, then open a second protected application without a new IdP prompt. A cookie-free/incognito context must still be intercepted.
9. Only after acceptance may One Agent disable/uninstall and device-registration cleanup be considered, under a separate LIVE authorization.

No source merge authorizes Cloudflare, credential, device, DNS, Tunnel, Worker, GitHub secret, or RPi5 runtime mutation.

## References

- https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/
- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/methods/update/
