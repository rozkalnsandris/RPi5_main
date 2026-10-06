# Phase 5 Deals IP Bypass remediation — source-only plan v1

Issue: [#895](https://github.com/rozkalnsandris/RPi5_main/issues/895). Parent runtime gate: [#866](https://github.com/rozkalnsandris/RPi5_main/issues/866).
Status: **SOURCE PLAN ONLY. No LIVE operation or operator with write credentials is provided.**

## Why this is blocked

The owner-authorized external GET-only run `37430551481` on 2026-10-06
classified `deals.rozkalns.net` with `bypass_policy_scope_class=scoped`
and `bypass_policy_selector_classes=["ip"]`. This shows the **type**
of selector, not its value or the policy's ownership model. The external
verifier must continue to return BLOCKED/UNKNOWN until the bypass is absent.
The prior route loopback and host isolation PASS receipts are historical
and must be refreshed after any eventual policy change.

Cloudflare documents two different policy resources:

- `GET /accounts/{account_id}/access/apps/{app_id}/policies` lists **both**
  application-specific/legacy and reusable policies attached to that application.
- `GET /accounts/{account_id}/access/policies` lists account-level reusable policies.
- `DELETE /accounts/{account_id}/access/apps/{app_id}/policies/{policy_id}`
  deletes an **application-specific** policy. It is not a general
  policy-association detach call for reusable policies.
- Account-level reusable-policy `DELETE` is **forbidden** for this remediation.
  Changing the reusable policy in place would impact every app that references it.
  For a reusable candidate, **STOP and review an app-only association-update plan**;
  do not guess the `PUT /access/apps/{app_id}` payload or perform a delete.

References:
- [List Access application policies](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/subresources/policies/methods/list/)
- [Delete an application-specific Access policy](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/subresources/policies/methods/delete/)
- [Manage reusable Access policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/policy-management/)
- [Strict service token authentication (2026-10-02)](https://developers.cloudflare.com/changelog/post/2026-10-02-strict-service-token-authentication/)

## Minimal source preflight — no API client, no host dependency

`scripts/phase5_deals_ip_bypass_source_preflight.py` exports a **pure**
`assess(...)` function. It does not read files, send requests, import a
credential client, call Wrangler or construct write requests. Synthetic
fixtures are in `tests/test-phase5-deals-ip-bypass-source-preflight.py`.

Only a **separately owner-authorized**, trusted future preflight may obtain
fresh Cloudflare GET results using the existing P1D03 **read-only** credential
lane, inside a protected execution context. The private snapshot must
remain transient; no raw policy data, account/app/policy IDs, IPs, selectors,
emails, auth-domain, AUD, tokens, or response body may enter GitHub evidence.

An authorized collector must prove complete pagination for:

1. `GET /accounts/{account_id}/access/apps` (all apps).
2. `GET /accounts/{account_id}/access/apps/{app_id}/policies` **for every
   app**; not only the Deals app, to detect shared references.
3. `GET /accounts/{account_id}/access/policies` (all reusable policies).
4. `GET /accounts/{account_id}/access/organizations` to classify strict
   service token authentication if a service-token dependency exists.

Use a fresh exact `RPi5_main/main` SHA, no unexpected branch drift and
current canonical ingress projection: only
`hermes-deals / deals.rozkalns.net` in PRIVATE/FAMILY_PRIVATE. Do not
treat `inventory_complete=true` supplied by an untrusted actor as proof.
The source-only module intentionally cannot certify collector provenance.

The module conservatively requires: one exact self-hosted Deals application
with no unexamined extra destinations; complete application-policy
inventories; policy IDs and unique precedence; exactly one Bypass whose
only Include selector type is `ip`; no extra Require/Exclude on the Bypass;
candidate absent from account-level reusable policies and every other
app's policy references; a separate narrow email-based human Allow policy;
an explicit decision whether machine/service-token authentication is
required; and when required, an existing Service Auth policy plus a
known organization strict-auth setting. `non_identity` does not by itself
prove a Service Auth path. Any ambiguity is **BLOCKED**.

A positive report is named **`SOURCE_ONLY_CANDIDATE`**, expressly NOT
`READY`, `LIVE-AUTH` or permission to use a write token. Reports emit
only bounded reason codes; all identifiers and selector values remain
inside the protected collector.

## Later one-shot remediation contract — NOT AUTHORIZED

Only after a fresh source merge + exact-main CI, a **separate exact-target
LIVE authorization** and a trusted protected runtime preflight may
a *newly reviewed* capability-specific mutator be implemented/used:

1. Revalidate exact main, complete Access inventory, exact target app and
   exactly one application-specific legacy IP Bypass ID. Confirm its exact
   action, Include/Require/Exclude, precedence and attachment relationships.
   Bind an immutable **private** prestate digest and target IDs in the
   protected execution context; public output remains sanitized. Verify
   intended family Allow and any genuinely needed Service Auth path.
2. Require explicit owner acceptance of potential home-IP access change,
   family/browser acceptance plan, affected-service window and recovery
   approach. No automatic rollback or alternate mutation is allowed.
3. Only in the proven *legacy, unshared* case, an exact app-specific policy
   removal is a possible **single forward mutation**. Do not delete a reusable
   policy or edit its global rules; do not alter other apps, wildcard, PUBLIC,
   ADMIN, DNS, Tunnel, routes, credentials, or service configuration.
   The exact DELETE is a **future reviewed design**, not code in this PR.
4. On HTTP error, timeout, ambiguity, changed prestate or uncertain commit:
   **STOP**, collect only bounded read-only evidence, then seek a fresh owner
   decision. Never retry, roll back or clean up automatically.
5. Independently refresh external Phase 5 GET-only proof
   (`bypass_policy_scope_class=absent`, anonymous challenge/deny, no
   ADMIN/PUBLIC overlap), V19 loopback route, host loopback listener/LAN
   absence, unaffected applications and recovery references. Separately
   authorize an owner-operated normal-browser FAMILY_PRIVATE receipt; if a
   service token is required, validate it under the actual strict-auth
   setting without disclosing secret material.

None of the above is performed by this source-only issue.
The protected browser path, Cloudflare policy write and any RPi5 or
Wrangler runtime operation each retain their original owner gates.
