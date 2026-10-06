# Phase 5 Deals Access IP Bypass mutator v1

Tracking: `RPi5_main#897`  
Parent remediation plan: `RPi5_main#895`  
Runtime verification parent: `RPi5_main#866`

Status: **SOURCE CAPABILITY ONLY** until a later explicit owner LIVE authorization binds an exact merged `main` SHA and `deals.rozkalns.net`.

## Purpose

This capability can remove exactly one proven **application-specific legacy IP Bypass** policy from the exact Cloudflare Access application for `deals.rozkalns.net`.

It is deliberately not a general Cloudflare writer. It cannot accept an arbitrary hostname, URL, API path, HTTP method, app ID, policy ID, account-level reusable-policy endpoint, DNS/Tunnel target, credential operation, or rollback command.

Cloudflare documents that:

- deleting an application-specific Access policy uses
  `DELETE /accounts/{account_id}/access/apps/{app_id}/policies/{policy_id}`;
- that operation requires `Access: Apps and Policies Write`;
- reusable policies are separate account-level resources and can be attached to multiple applications;
- editing a reusable policy affects every associated application.

Therefore this capability **never** calls the reusable-policy DELETE endpoint and blocks any candidate whose policy ID appears in the reusable-policy inventory or another application's policy inventory.

Cloudflare's current response schemas mark policy `id` as optional for both application-policy and reusable-policy list responses, and `app_count` as optional for reusable policies. The destructive proof normalizes those documented shapes without treating missing identity as success:

- every application-policy entry must still expose a valid stable policy ID; otherwise the result is `application_policy_identity_unproven` because cross-application sharing cannot be excluded;
- a reusable-policy entry with a valid ID is compared normally;
- a reusable-policy entry with no ID is accepted only when Cloudflare explicitly reports integer `app_count == 0`, proving it is attached to no application;
- missing/invalid reusable ID with absent, unknown, malformed or positive `app_count` returns `reusable_policy_identity_unproven`;
- the reusable `app_count` is included in the protected prestate digest/post-write comparison and is never emitted publicly.

References:
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/subresources/policies/methods/delete/
- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/policy-management/
- https://developers.cloudflare.com/changelog/post/2026-10-02-strict-service-token-authentication/

## Source surfaces

- `scripts/cloudflare_phase5_deals_ip_bypass_remove.py` — GET snapshot, fail-closed plan, private prestate binding, exactly-one DELETE client and post-write proof.
- `scripts/cloudflare_phase5_deals_ip_bypass_remove_actions.py` — GitHub Actions-only secret handling and exact-main gate.
- `scripts/github_phase5_deals_ip_bypass_remove_bridge.py` — direct-owner, issue `#897`, exact-SHA, first-attempt-only authorization bridge.
- `.github/workflows/cloudflare-phase5-deals-ip-bypass-remove.yml` — reuses the existing P1D04 Access read/write secret lane.
- `tests/test-phase5-deals-ip-bypass-remove.py` — synthetic/offline adversarial tests.

No new Cloudflare credential, secret name, permission, service, RPi5 helper, Wrangler command, generic dispatcher or runtime daemon is introduced.

## Read-only inventory diagnostic

After a preflight result such as `access_application_inventory_empty`, use the separate owner-gated diagnostic workflow before another removal attempt. It loads only the existing P1D03/P1D04 account IDs and **read** tokens and performs GET-only token verification plus `/access/apps` listing for both lanes.

Public output is restricted to booleans/classes:
- whether P1D03/P1D04 account bindings match;
- whether each lane sees any Access applications;
- whether each lane resolves exactly one `deals.rozkalns.net` application;
- whether the two lanes see the same application inventory and Deals application identity.

It never loads a write token, never emits account/app IDs or raw responses, and has no mutation method.

## Future LIVE command contract

A later LIVE operation may be triggered only by a new direct owner comment on issue `#897` matching exactly:

`/rpi5-p5-deals-ip-bypass-remove apply HEAD=<exact-main-sha> CANARY=phase5-deals-ip-bypass-remove-v1`

The workflow itself then requires:

1. issue-comment event created by the repository owner, never a GitHub App;
2. run attempt `1` only;
3. workflow `GITHUB_SHA` equal to the command's immutable SHA;
4. current GitHub `main` still equal to that SHA;
5. required exact-main workflows green;
6. existing P1D04 account/read/write secrets present, distinct read/write tokens and both tokens active;
7. default Cloudflare API base only.

A merged source capability or a GitHub comment generated without a current explicit owner LIVE decision is **not authorization**.

## Protected preflight

The read client obtains a complete paginated Access snapshot:

- all Access applications;
- every application's policy list;
- all account-level reusable policies;
- Access organization state.

All raw values remain inside the protected Actions process. Public output never includes account/app/policy IDs, selector values, IPs, identities, token values, raw payloads or the private prestate digest.

The candidate is BLOCKED unless all of the following hold:

- exact target is `deals.rozkalns.net`;
- exactly one matching self-hosted application and no unexamined destination scope;
- complete policy inventory exists for every application;
- exactly one Bypass exists on Deals;
- that Bypass has one Include rule whose only selector class is `ip`;
- Bypass has no Require/Exclude rules;
- policy IDs and precedence are unambiguous;
- candidate policy ID is absent from account reusable policies and from all other app policy lists;
- a separate narrow email-selector human Allow policy remains present with no Require/Exclude rules;
- a separate Service Auth policy remains present using only a service-token Include selector, with no Require/Exclude rules;
- `strict_service_token_auth` is explicitly present as a boolean in organization state.

Immediately before DELETE, the workflow performs the same complete GET inventory a second time. A private canonical digest plus target IDs must match the first snapshot exactly. Any drift blocks **before** mutation.

## Only permitted mutation

After the double-read equality gate, the write client may dispatch exactly one request:

`DELETE /accounts/{account_id}/access/apps/{exact_deals_app_id}/policies/{exact_legacy_bypass_policy_id}`

There is no loop, retry, fallback, alternate endpoint, PUT/PATCH, account reusable DELETE or cleanup action.

If the request returns an HTTP error, times out, produces an invalid response or has an uncertain result, the workflow returns `STOP_ERROR` and performs no retry or rollback.

If the existing P1D04 write token lacks `Access: Apps and Policies Write`, the expected safe outcome is an authorization failure from Cloudflare and `STOP_ERROR`; this source capability does not alter token permissions.

## Post-write proof

After one successful DELETE, a fresh read-only snapshot must prove:

- exact app projection unchanged;
- only the exact target policy disappeared from the Deals policy list;
- every other application's policy projection unchanged;
- account reusable-policy projection unchanged;
- organization strict service-token state unchanged;
- no Bypass remains on Deals;
- strict family Allow remains;
- strict Service Auth remains.

Failure of any post-write proof returns `STOP_ERROR`. Because mutation may already have occurred, repository fail-closed rules require a new owner decision before any retry, rollback, cleanup or alternate mutation.

## Separate acceptance after mutation

A successful API-state proof is not Phase 5 completion by itself. Under the existing gates, refresh:

1. Phase 5 external GET-only verification — Bypass absent and anonymous request challenged/denied;
2. V19 route verification — loopback and no route mutation;
3. RPi5 host isolation — loopback listener and absent direct LAN path;
4. owner-operated normal-browser FAMILY_PRIVATE acceptance;
5. if service-token automation is genuinely required, its path under the actual strict-auth setting without exposing credentials.

Only those independent fresh proofs can complete parent issue `#866`.
