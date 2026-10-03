# Cloudflare RDC operator v1

Status: **SOURCE-ONLY / HOST INSTALL + SECRET PROVISIONING REQUIRED**  
Canonical issue: `RPi5_main#841`  
Machine contract: `ops/contracts/cloudflare-rdc-operator-v1.json`

## Purpose

This operator is the reviewed host-side boundary for future Cloudflare control-plane changes launched through RDC. RDC remains transport only: it does not grant Cloudflare authority, secret access, arbitrary root shell authority, or caller-selected API requests.

The source bootstrap deliberately starts with one operation only:

```text
access-public-bypass coloring.rozkalns.net
```

That operation exists to resolve the current `homelab-private` `*.rozkalns.net` capture while preserving the wildcard and all unrelated Access, Tunnel, DNS and host state.

## Current Cloudflare API semantics

Verified against current Cloudflare documentation on 2026-10-03:

- a self-hosted Access application can be created with `POST /accounts/{account_id}/access/apps`;
- the create payload may contain an inline application-exclusive policy, so the exact application plus `Bypass` / `Everyone` policy can be one write request;
- `Access: Apps and Policies Edit` is the least-privilege account capability for the Access lane (Cloudflare API reference pages may render the accepted permission as `Access: Apps and Policies Write`);
- a more-specific Access application takes precedence over a broader wildcard application;
- a `Bypass` policy with `Everyone` makes the matching application public and disables Access enforcement/logging for that matching traffic, so it must be scoped to the exact public hostname.

Official references:

- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/methods/create/
- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/common-policies/
- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/

## Root and secret boundary

The reviewed source entrypoint is:

```text
scripts/cloudflare_rdc_operator.py
```

A later, separately authorized host-install operation must materialize the exact reviewed source as a root-owned installed entrypoint:

```text
/usr/local/sbin/rpi5-cloudflare
```

and write root-owned release metadata at:

```text
/usr/local/libexec/rpi5-cloudflare/release.json
```

The release metadata binds the installed operator SHA-256 to the exact reviewed `RPi5_main` commit. Runtime `--expected-main` must equal that installed release SHA. Fresh GitHub `main` validation remains an external preflight before any LIVE authorization; the root operator never treats local repository state as authority.

No credential is accepted from argv or environment. The Access lane reads only the fixed root-owned `0600` file:

```text
/etc/rpi5-secrets/cloudflare/access-writer.json
```

with exactly these private keys:

```json
{"account_id":"<private>","api_token":"<private>"}
```

The file content must never be read, printed, copied into chat, committed, attached to GitHub evidence, or inspected through RDC. The operator consumes it internally and emits only sanitized booleans/status classes.

## Capability lanes

Credentials are split by capability. There is intentionally no master token.

| Lane | Secret path | Cloudflare capability | v1 implementation |
|---|---|---|---|
| Access | `/etc/rpi5-secrets/cloudflare/access-writer.json` | `Access: Apps and Policies Edit` | implemented |
| Tunnel | `/etc/rpi5-secrets/cloudflare/tunnel-writer.json` | `Cloudflare Tunnel Edit` | reserved, not implemented |
| DNS | `/etc/rpi5-secrets/cloudflare/dns-writer.json` | `DNS Edit`, restricted to `rozkalns.net` | reserved, not implemented |

The operator must never receive `API Tokens Edit`. Token creation/rotation and secret provisioning are separate owner-gated operations.

## Coloring Pages operation

Read-only preflight requires all of the following:

1. exact `coloring.rozkalns.net` Access application is absent;
2. exactly one `homelab-private` self-hosted application covers root `*.rozkalns.net`;
3. the bounded application inventory is complete;
4. installed release metadata matches the owner-authorized exact `main` SHA;
5. the Access capability secret is root-owned, `0600`, bounded and schema-valid.

The only allowed write is one request:

```text
POST /accounts/{account_id}/access/apps
```

with the fixed semantic payload:

```json
{
  "name": "Coloring Pages Public",
  "type": "self_hosted",
  "destinations": [{"type": "public", "uri": "coloring.rozkalns.net"}],
  "policies": [{
    "name": "public-access",
    "decision": "bypass",
    "include": [{"everyone": {}}]
  }]
}
```

No caller-selected hostname, app name, policy, selector, path, endpoint or request body is accepted.

After a successful POST, verification is GET-only. It requires exactly one target application, exactly one `Bypass` policy containing only `Everyone`, no `Require`/`Exclude` rules, and unchanged semantic projections for all pre-existing applications.

## CLI contract

Read-only preflight:

```bash
sudo -n /usr/local/sbin/rpi5-cloudflare access-public-bypass coloring.rozkalns.net \
  --expected-main <40-character-reviewed-main>
```

The later exact LIVE command adds both mutation switches:

```bash
sudo -n /usr/local/sbin/rpi5-cloudflare access-public-bypass coloring.rozkalns.net \
  --expected-main <40-character-reviewed-main> \
  --apply \
  --confirm CREATE-COLORING-PUBLIC-BYPASS
```

The host install, any sudoers capability, Access token creation, secret provisioning and the LIVE apply remain separate owner gates. Merging this source does none of them.

## Failure semantics

Before the POST, any mismatch is `BLOCKED` and no mutation occurs.

Once the POST is attempted:

- transport/HTTP/response ambiguity => `STOP_ERROR`, mutation state unknown;
- successful POST followed by verification failure => `STOP_ERROR`, mutation known to have started;
- no retry;
- no DELETE cleanup;
- no rollback;
- no second write;
- no alternate token/path/API endpoint.

Only minimum sanitized read-only evidence may be collected after a write failure, followed by a new explicit owner decision.

## Future expansion

Tunnel and DNS actions must be added by reviewed source changes with their own fixed request models, capability secrets, tests, mutation budgets and owner gates. The Access token is never reused as a general Cloudflare token, and future lanes must not widen the v1 Access action.
