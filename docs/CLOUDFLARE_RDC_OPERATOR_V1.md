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
- `Access: Apps and Policies Write` is the current account-level permission accepted by the Access application/policy write endpoints;
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
| Access | `/etc/rpi5-secrets/cloudflare/access-writer.json` | `Access: Apps and Policies Write` | implemented |
| Tunnel | `/etc/rpi5-secrets/cloudflare/tunnel-writer.json` | `Cloudflare One Connector: cloudflared Write` | reserved host consumer of the shared Tunnel operator, not implemented |
| DNS | `/etc/rpi5-secrets/cloudflare/dns-writer.json` | `DNS Edit`, restricted to `rozkalns.net` | reserved, not implemented |

The Tunnel lane is intentionally **one reusable capability credential for Tunnel operations**, not one credential per project or per action. In the current Cloudflare dashboard the canonical permission is `Cloudflare One / Zero Trust` → `Cloudflare One Connector: cloudflared` → `Edit`. Its canonical source contract is `ops/contracts/cloudflare-tunnel-operator-v1.json`. Reviewed read-only consumers may use the same Tunnel credential but remain GET-only in their own source contracts; any write consumer must define an operation-specific request model, exact target, mutation budget and fresh explicit owner authorization. The Tunnel credential is never reused for Access or DNS.

The operator must never receive `API Tokens Edit`/`API Tokens Write`. Token creation/rotation remains a separate owner action. The provisioning action can verify that the supplied token is active and can read the Access application surface, but it cannot prove the absence of additional undisclosed token permissions without granting broader token-introspection authority. The owner must therefore create the token with only `Access: Apps and Policies Write`.

## Reviewed host installer

The source-only installer is:

```text
scripts/install-cloudflare-rdc-operator.py
```

It is deliberately an **unprivileged repository controller**. Running the repository Python itself as root is rejected. Before any install it requires:

- a clean checkout of canonical `rozkalnsandris/RPi5_main`;
- branch `main`;
- local `HEAD` exactly equal to the owner-authorized 40-character `main` SHA;
- canonical `origin`;
- the operator source tracked by Git;
- non-interactive `sudo` availability;
- all three install targets absent.

Read-only install preflight:

```bash
python3 scripts/install-cloudflare-rdc-operator.py \
  --expected-main <40-character-reviewed-main>
```

A later exact LIVE authorization may add:

```bash
python3 scripts/install-cloudflare-rdc-operator.py \
  --expected-main <40-character-reviewed-main> \
  --apply \
  --confirm INSTALL-CLOUDFLARE-RDC-OPERATOR
```

The installer may create only:

- `/usr/local/libexec/rpi5-cloudflare/` as `root:root 0700`;
- `/usr/local/sbin/rpi5-cloudflare` as `root:root 0500`;
- `/usr/local/libexec/rpi5-cloudflare/release.json` as `root:root 0400`.

It does not install or modify sudoers. It uses the host's already-authorized sudo transport and fails closed if non-interactive sudo is unavailable. After the first install mutation, any command or verification error is `STOP_ERROR`; there is no retry, overwrite, removal or rollback.

## Reviewed exact-release operator upgrade

An already-installed operator is never overwritten by the initial-install path. A reviewed upgrade requires both the new exact checkout SHA and the exact currently installed release SHA.

Read-only upgrade preflight:

```bash
python3 scripts/install-cloudflare-rdc-operator.py \
  --expected-main <40-character-new-reviewed-main> \
  --upgrade-from <40-character-exact-installed-release>
```

A later exact LIVE authorization may add:

```bash
python3 scripts/install-cloudflare-rdc-operator.py \
  --expected-main <40-character-new-reviewed-main> \
  --upgrade-from <40-character-exact-installed-release> \
  --apply \
  --confirm UPGRADE-CLOUDFLARE-RDC-OPERATOR
```

Preflight requires a clean canonical `main` checkout at the new SHA and validates, without reading any Cloudflare secret, that the installed operator is `root:root 0500`, release directory is `root:root 0700`, release metadata is `root:root 0400`, metadata `source_sha` equals the exact `--upgrade-from` SHA, and the installed operator SHA-256 equals the metadata hash.

The apply path dispatches one fixed root helper. Immediately before its first mutation, that helper revalidates the exact old release and fixed paths. New operator and metadata bytes are staged only at:

```text
/usr/local/sbin/rpi5-cloudflare.next
/usr/local/libexec/rpi5-cloudflare/release.json.next
```

Both staged files are hash/mode validated before atomic replacement of the installed operator and release metadata. Existing stage files block the upgrade. If the root helper is dispatched and returns any error, the installer reports `STOP_ERROR`; there is no retry, delete, cleanup or rollback. A partially completed replacement is therefore deliberately fail-closed and requires a new owner decision.

The upgrade path does not modify sudoers, read or write Cloudflare credentials, or call Cloudflare APIs.

## Local Access secret provisioning

After the exact reviewed operator is installed, secret provisioning is performed by that **installed root-owned operator**, not by repository Python and not through an RDC payload.

The fixed command is:

```bash
sudo -n /usr/local/sbin/rpi5-cloudflare provision-access-secret \
  --expected-main <40-character-reviewed-main> \
  --confirm PROVISION-CLOUDFLARE-ACCESS-SECRET
```

This command must be launched from a human-controlled local/SSH terminal with a controlling TTY. Before prompting, the operator opens `/dev/tty` with the low-level `os.open` interface and requires `os.isatty` to pass. It then calls Python's native `getpass.getpass()` **without a custom stream**, allowing the standard library to use the controlling terminal itself. Any `GetPassWarning`, EOF, keyboard interruption or TTY error is converted to `local_tty_required`; echoed `sys.stdin` fallback is never accepted.

This matches Python's documented Unix behavior: with `stream=None`, `getpass` uses the controlling terminal (`/dev/tty`) and issues `GetPassWarning` if echo-free input cannot be provided.

Official reference:

- https://docs.python.org/3.12/library/getpass.html

It prompts with terminal echo disabled for:

1. Cloudflare account ID;
2. the one-time API token created with **only** `Access: Apps and Policies Write`.

The account ID and token are not accepted in argv or environment variables. They must not be pasted into ChatGPT, RDC commands, GitHub, logs or files outside the fixed root-only secret destination.

Before the first filesystem mutation, the installed operator performs only read-only Cloudflare checks:

- `GET /user/tokens/verify` must report the token active;
- `GET /accounts/{account_id}/access/apps` must succeed.

If those checks pass and no secret already exists, provisioning may create the required root-only parent directories when absent and then exclusively create:

```text
/etc/rpi5-secrets/cloudflare/access-writer.json
```

as `root:root 0600`. Existing secret files are never overwritten. After the first directory/file mutation, any error is `STOP_ERROR`; no automatic retry, delete, rollback or cleanup is performed.

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

The host install, Access token creation, local secret provisioning and the LIVE apply remain separate owner gates. This source does not add a sudoers rule. Merging it performs none of those operations.

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
