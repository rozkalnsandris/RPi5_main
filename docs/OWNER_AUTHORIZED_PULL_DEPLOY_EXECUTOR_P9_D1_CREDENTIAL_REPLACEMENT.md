# Owner-authorized deploy executor — P9 Control D1 credential replacement

Status: **SOURCE ONLY / LIVE TOKEN CREATION AND HOST CREDENTIAL REPLACEMENT NOT AUTHORIZED BY MERGE**

## Why this contract exists

Canonical issue `#191` records a Gate C STOP: the existing P9 Control baseline D1 credential cannot currently be tied to a provider-side `D1 Read`-only token. The inspected legacy candidate `rozkalns-control-setup` has `D1 Edit` plus unrelated `Edit` permissions and must not be repurposed in place because it may have other consumers.

The existing provisioning operator remains intentionally create-only. This document adds a separate replacement path for the already-present fixed credential without weakening that original contract.

## Target capability

The replacement candidate must be a newly owner-created **Cloudflare Account API Token** owned by exactly this account:

`70e29dbca0e8363358659102d2b74178`

Provider-side policy must be proven separately before host replacement:

- account resource: exactly the account above;
- permission: exactly `Account / D1 / Read`;
- no `D1 Edit`, write permission, or unrelated permission group;
- token status: active;
- record the public-safe Cloudflare token ID for the exact token object;
- never put the token secret in GitHub, chat, argv, environment variables, logs, or evidence.

Cloudflare token creation/permission selection is a separate LIVE trust-surface gate. Source merge does not authorize it.

## Reviewed replacement operator

Future separately authorized STRICT LIVE host replacement uses:

`python3 scripts/replace-deploy-executor-p9-control-d1-read-token.py <exact-reviewed-rpi5-main-sha> <expected-token-id>`

The expected token ID is public-safe provider metadata. It is not the secret.

The operator accepts the candidate secret only through a hidden interactive TTY prompt. It keeps token bytes only in process memory and never prints them.

### Fixed host target

Only this existing file may be replaced:

`/root/.config/rozkalns-deploy-executor-p9/control-d1-read-token`

Required prestate:

- root execution;
- exact reviewed RPi5_main `HEAD`;
- the replacement operator itself clean against that exact SHA;
- `/root/.config` is a root-owned real directory with no group/world write bits;
- credential directory is a real root:root `0700` directory;
- credential target is a regular non-symlink root:root `0400` file;
- target size is within the same bounded opaque-token envelope used by the collector;
- stdin and stderr are interactive TTYs.

The operator deliberately **does not read the old credential contents**. It proves only fixed-path inode and metadata prestate before replacement.

## Candidate identity proof before mutation

Before changing the credential file, the operator makes exactly one candidate-token verification request:

`GET https://api.cloudflare.com/client/v4/accounts/70e29dbca0e8363358659102d2b74178/tokens/verify`

Properties:

- fixed HTTPS host and exact account path;
- `Authorization: Bearer <hidden candidate>` exists only in process memory;
- no redirect-following layer;
- no retry loop;
- bounded response size;
- response body/provider message/raw exception is never emitted;
- HTTP 200 + `success=true` + object result required;
- returned token ID must equal the separately supplied expected token ID;
- returned status must be `active`.

This verification proves that the hidden candidate secret authenticates as the exact account-owned token object whose public-safe policy was separately reviewed. It **does not** itself prove permission policy, so the provider-side `D1 Read`-only receipt remains a required prerequisite.

The future replacement authorization is consumed immediately before this request. Any failure after that marker is STOP/no retry.

No D1 database request is made by this proof.

## One-target mutation

Only after candidate identity verification passes, the operator repeats the exact source and target race gates.

The target is opened write-only with no-follow/close-on-exec guards and exact inode/metadata matching. Mutation begins at the first `ftruncate` and consists only of:

1. truncate the already-open fixed target;
2. write the validated candidate bytes plus one newline;
3. `fsync`;
4. verify the same inode remains root:root `0400` with the exact new size.

There is intentionally:

- no temp file;
- no rename/replace/unlink;
- no backup copy of the old secret;
- no rollback path;
- no cleanup path;
- no automatic retry.

Therefore any error after mutation begins is fail-closed and requires a new owner decision. Do not automatically repair or restore the old secret.

## Explicit non-capabilities

The operator does not:

- create, update, rotate, disable, or delete a Cloudflare token;
- inspect Cloudflare token permission policy;
- read old credential bytes;
- make a D1 database request;
- collect or publish a baseline;
- mint a GitHub App token;
- execute P9;
- touch StateStore;
- change systemd/services/timers;
- change config/registry;
- touch queue or LIVE-AUTH state;
- deploy anything.

## Expected public-safe markers

Successful future execution includes:

- `PRE_NETWORK_GATE=PASS`;
- `AUTHORIZATION_CONSUMED=YES operation=d1_credential_candidate_token_verify`;
- `TOKEN_VERIFY=PASS`;
- `P9_CONTROL_D1_CREDENTIAL_REPLACEMENT=PASS`;
- `CREDENTIAL_INPUT=HIDDEN_TTY`;
- `OLD_CREDENTIAL_CONTENT_READ=NO`;
- `TOKEN_VERIFY_REQUEST=YES`;
- `D1_REQUEST=NO`;
- `CLOUDFLARE_PERMISSION_MUTATION=NO`;
- `BASELINE_COLLECTION=NO`;
- `P9_EXECUTION=NO`;
- `STATE_STORE_TOUCHED=NO`;
- `ROLLBACK_PATH=NO`;
- `RETRY_PATH=NO`.

The public-safe receipt may contain the exact account ID and expected/verified token ID. It must never contain token secret bytes or a response body.

## Required continuation sequence

1. Merge this source only after explicit owner MERGE authorization and exact-main CI.
2. Separately authorize Cloudflare creation of one dedicated account-owned token with exactly `D1 Read` for account `70e29dbca0e8363358659102d2b74178`; do not edit the legacy broad token merely for P9.
3. Capture metadata-safe provider evidence for exact token ID, active status, exact account and exact `D1 Read`-only policy. Secret stays off chat/GitHub/logs.
4. Separately authorize trusted-RPi5 checkout sync plus exactly one invocation of the reviewed replacement operator, binding exact source SHA and expected token ID.
5. Re-run Gate C metadata-safe least-privilege proof against the same token ID.
6. Gate D baseline production remains separately unauthorized until Gate C is green.

Source review or merge authorizes none of steps 2–6.
