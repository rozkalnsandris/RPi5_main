# V20 Hermes Tech HTTP policy production activation

## Status

**Source-controlled production operator gate.**

Merging the operator performs no production mutation. The operator is run later
on the RPi5 against an explicit, exact merged `RPi5_main` SHA.

This activation implements the production phases already defined by
`V20_HERMES_TECH_HTTP_POLICY_CONTRACT.md`; it does not change the HTTP policy.

The policy source baseline is the merged V20 commit:

`f873a9dff27a6954f02739a55aa7031a26d56267`

## Why this operator exists

The V20 source merge deliberately did not install or restart anything on the
host. Production activation needs host state that GitHub-hosted CI cannot
observe: the installed unit, retained local Nginx image, current `hermes-blog`
container, loopback-only bind, public health, and shared Cloudflare connector
identity.

The production work therefore remains host-operated, but the commands and
allowed mutation surface are source-controlled and regression-tested.

## Operator

`ops/bin/hermes-tech-http-policy-v20`

Every invocation requires:

`--expected-sha <exact merged RPi5_main SHA>`

The operator requires the local checkout to be clean `main`, with both `HEAD`
and `refs/remotes/origin/main` equal to that SHA. It also requires the original
merged V20 source commit above to be an ancestor.

Run the operator as root only after the non-root checkout has been fetched and
fast-forwarded to the approved exact SHA.

## Phases

### `check`

Read-only production preflight.

It proves:

- exact clean Git source;
- reviewed V20 source invariants;
- the retained exact local Nginx image is present;
- the reviewed Nginx configuration passes `nginx -t` in an isolated,
  `--pull=never`, network-disabled temporary container;
- the currently installed unit is the accepted pre-V20 V14 unit;
- `hermes-tech-web.service` is active and enabled;
- `hermes-blog` still uses the exact image, `restart=no`,
  `127.0.0.1:8089:80`, the read-only Hugo public bind and bounded logging;
- loopback/public home, the 2026-08-08 representative digest and RSS are
  HTTP 200;
- direct LAN access to port 8089 remains unavailable;
- `cloudflared.service` is active/enabled with HA 4/4.

`check` writes nothing to `/etc`, systemd, Docker production state, UFW or the
shared tunnel.

### `install`

This is the **install-only** phase.

Before replacing any file it records the exact pre-V20 unit, owner/mode/hash,
live container identity, shared `cloudflared.service` PID/HA, source hashes and
approved Git SHA below:

`/var/lib/rpi5-main/hermes-tech-http-policy-v20`

It then:

1. installs `ops/nginx/hermes-tech.conf` as
   `/etc/rpi5-hermes-tech-nginx.conf`, `root:root`, mode `0644`;
2. installs `ops/systemd/hermes-tech-web.service` as
   `/etc/systemd/system/hermes-tech-web.service`, `root:root`, mode `0644`;
3. verifies source/installed SHA-256 identity;
4. runs `systemd-analyze verify`;
5. runs `systemctl daemon-reload`;
6. verifies health, shared-tunnel identity and the original live container
   identity.

**It does not restart, stop or start `hermes-tech-web.service`.**

A successful install ends with:

`HERMES_TECH_V20_ACTIVATION_INSTALL=PASS`

### `canary`

The canary is a **separate invocation after a successful install-only phase**.

It re-verifies exact source/state first, then restarts only
`hermes-tech-web.service`. It requires the recreated `hermes-blog` container to
have the exact reviewed V20 runtime identity and checks:

- loopback/public home, representative article and RSS;
- fingerprinted Hugo CSS:
  `Cache-Control: public, max-age=31536000, immutable`;
- HTML/RSS stable URLs: `Cache-Control: no-cache`;
- exact CSP, `X-Content-Type-Options`, `Referrer-Policy` and
  `Permissions-Policy`;
- no conflicting duplicate policy headers;
- direct LAN origin still blocked;
- the shared `cloudflared.service` PID and HA remain unchanged from the
  pre-install capture.

If a post-restart canary assertion fails, the operator automatically attempts
the bounded rollback described below and reports whether that rollback passed.

A successful canary ends with:

`HERMES_TECH_V20_ACTIVATION_CANARY=PASS`

### `verify`

Read-only post-canary verification. It repeats the runtime, public, loopback,
header and tunnel-identity assertions and writes only protected evidence.

A successful verification ends with:

`HERMES_TECH_V20_ACTIVATION_VERIFY=PASS`

### `rollback`

Restores the protected pre-V20 V14 unit, reloads systemd and restarts only
`hermes-tech-web.service`. It verifies the old unit checksum, exact retained
image, loopback-only publish, loopback/public health and the unchanged shared
tunnel identity.

The new root-owned Nginx config may remain on disk as inactive rollback
evidence because the restored V14 unit does not mount it.

## Mutation boundary

The operator may:

- create protected V20 state/backup evidence under `/var/lib/rpi5-main`;
- install the two reviewed V20 host files;
- run `systemctl daemon-reload`;
- restart only `hermes-tech-web.service` during `canary` or `rollback`;
- run an isolated temporary `nginx -t` container with the already-present exact
  image and `--pull=never`.

The operator must not:

- pull, upgrade, prune or delete Docker images;
- restart/reload/reconfigure `cloudflared.service`;
- mutate UFW, Cloudflare routes/DNS/Access, or any shared tunnel setting;
- change Hermes Tech content, digests, database or scheduling;
- reboot/shutdown the host;
- push, rebase or rewrite Git history.

## Acceptance

Production V20 is complete only when `check`, `install`, the separately invoked
`canary`, and `verify` have passed from one approved exact Git SHA and the
resulting evidence is recorded in the RPi5 and Hermes Tech T9 ledgers.
