# Owner-authorized deploy executor — P9 Control D1 credential provisioning

Status: **SOURCE ONLY / LIVE CREDENTIAL PLACEMENT NOT AUTHORIZED BY MERGE**

## Purpose

Define one narrow, fail-closed operator for placing the owner-supplied Control D1 credential required by P9 trusted baseline collection.

The reviewed operator is:

`python3 scripts/provision-deploy-executor-p9-control-d1-read-token.py <exact-reviewed-rpi5-main-sha>`

It is a future STRICT LIVE action. Source merge alone never authorizes invocation.

## Secret ingress boundary

The credential value must never be supplied through:

- command-line arguments;
- environment variables;
- GitHub issues, PRs, comments, Actions inputs or artifacts;
- ChatGPT/chat text;
- shell command text or shell history;
- stdout/stderr logs.

The operator accepts the owner-supplied opaque credential only from an interactive hidden TTY prompt after all possible pre-mutation checks pass. It does not create, rotate, query or inspect Cloudflare API-token policy. Provider-side token creation and least-privilege policy selection remain outside this operator and require their own explicit owner decision where applicable.

The source contract deliberately does not assert that Cloudflare exposes a particular provider-side permission granularity. Runtime capability is further constrained by the separately reviewed fixed D1 client, which permits only the source-fixed SELECT statements and requires zero-write response metadata.

## Fixed target

Only this path is writable by the operator:

`/root/.config/rozkalns-deploy-executor-p9/control-d1-read-token`

The parent credential directory is fixed to:

`/root/.config/rozkalns-deploy-executor-p9`

Preconditions:

- exact checkout HEAD equals the supplied reviewed SHA;
- the provisioning operator itself is clean against that exact SHA;
- execution identity is root;
- `/root/.config` is an existing root-owned non-symlink directory and is not group/world writable;
- the fixed credential directory, when already present, is root:root mode `0700` and non-symlink;
- the credential target does not already exist in any form;
- interactive stdin/stderr TTYs are present;
- the opaque credential is UTF-8, 20–4096 bytes, and contains no whitespace.

Existing target state always fails closed. This operator has no overwrite, replace, rotation, cleanup or rollback path.

## Mutation envelope

After a final duplicate source/path race gate, the only allowed mutations are:

1. create the fixed credential directory as root:root `0700` if and only if it is absent;
2. create the fixed credential file exactly once as root:root `0400` using exclusive, no-follow file creation;
3. write the already validated opaque credential plus one terminating newline and fsync it.

The first directory/file creation consumes the future Composite LIVE authorization. Any error after that point is STOP with no automatic retry, cleanup, deletion, replacement or alternate path.

The operator never:

- performs a D1 request;
- mints a GitHub App installation token;
- verifies or changes source-App repository scope;
- runs trusted baseline collection/production;
- runs the P9 canary;
- opens or mutates the P9 StateStore;
- changes services/timers, Docker, networking, firewall, DNS, Cloudflare configuration, users/groups or sudo policy;
- creates or modifies GitHub/Cloudflare permissions.

## Postconditions

A successful invocation prints only public-safe status markers and the exact reviewed source SHA. It never prints the credential or credential-derived material.

Expected success markers:

- `P9_CONTROL_D1_CREDENTIAL_PROVISION=PASS`;
- `CREDENTIAL_INPUT=HIDDEN_TTY`;
- `CREDENTIAL_OVERWRITE=NO`;
- `D1_REQUEST=NO`;
- `BASELINE_COLLECTION=NO`;
- `P9_EXECUTION=NO`;
- `STATE_STORE_TOUCHED=NO`.

After successful placement, source-App live scope proof and SELECT-only trusted baseline collection remain separate reviewed prerequisites. Genuine P9 still requires a fresh owner-authored LIVE-AUTH and a separate exact P9 dry-run authorization.
