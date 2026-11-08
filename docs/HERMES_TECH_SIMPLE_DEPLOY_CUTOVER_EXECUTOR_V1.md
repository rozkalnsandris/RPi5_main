# Hermes Tech SIMPLE-DEPLOY cutover executor v1

Issue: `#1447`  
Target: `hermes-tech-public-rpi5`  
Status: **SOURCE-ONLY / NOT INSTALLED / NOT ACTIVATED**

## Purpose

The existing Hermes Tech one-time cutover contract already freezes the legacy
runtime, reviewed SIMPLE-DEPLOY target, Compose identity, loopback port and
fail-closed semantics. This outcome adds the missing fixed execution path so a
future exact owner-authorized LIVE operation does not need generic root/shell
or caller-selected path/command authority.

Source merge alone performs no RPi5 mutation.

## Fixed source closure

The reviewed closure is exactly:

- installer: `ops/bin/install-hermes-tech-simple-deploy-cutover-v1`;
- root cutover operator: `ops/bin/hermes-tech-simple-deploy-cutover-v1`;
- non-root exact-release adapter: `ops/bin/hermes-tech-exact-reconcile-v1`;
- contract: `ops/deploy/hermes-tech-simple-deploy-cutover-v1.json`;
- static target: `hermes-tech-public-rpi5`;
- reviewed Compose SHA-256:
  `fd1ca0d00c79bfb5e5cd1be589ae13b378c5c223be0b61d3f14f31da687fe6b9`.

The future installer accepts only an exact `RPi5_main` SHA and a fixed
confirmation token. It reads the three tracked source blobs from a clean,
canonical, exact-main checkout and may create only two fixed installed files:

- `/usr/local/libexec/rozkalns-simple-deployer/hermes-tech-exact-reconcile-v1`
  as root:root `0555`;
- `/usr/local/sbin/hermes-tech-simple-deploy-cutover-v1`
  as root:root `0500`.

Support is published first and the root entrypoint last. A partial support-only
install is inert. Destinations must be absent. There is no replace, cleanup,
rollback or retry path.

## Generic SIMPLE-DEPLOY reuse

The cutover does **not** fork or extend the ordinary
`simple_deploy_v1.py` CLI. The installed generic module remains the deployment
state machine.

The exact-release adapter runs as `rozkalns-simple-deployer`, loads only the
fixed installed generic module, verifies the reviewed compatible installed
identity and SHA-256, and fixes the target to
`hermes-tech-public-rpi5`.

Its only release inputs are:

- the exact authorized Hermes Tech source SHA;
- the exact authorized immutable `sha256:...` image digest.

Before Docker/Compose mutation it requires the `:production` discovery pointer
to equal that digest and image metadata to bind the same source SHA, target alias
and reviewed shared-workflow SHA. After the generic reconciliation it also
requires the discovery pointer to remain the same digest. Drift is STOP, never
permission to deploy another release.

## One-time cutover order

A future Composite LIVE may proceed only after fresh exact-main CI and
minimum-sufficient host preflight prove the reviewed baseline. The fixed
operator order is:

1. prove installed operator/helper bytes equal the exact authorized main Git blobs;
2. prove the installed generic SIMPLE-DEPLOY identity/module matches the reviewed compatible baseline;
3. prove the authorized Hermes Tech source/digest is exactly what GHCR
   `:production` currently resolves to;
4. prove legacy `hermes-tech-web.service` and
   `hermes-tech-pull-deploy.timer` are in the reviewed active baseline and
   the pull service is stable, not transitioning;
5. prove the exact legacy `hermes-blog` image owns
   `127.0.0.1:8089`;
6. prove the new Compose destination and success receipt are absent;
7. prove the target-scoped SIMPLE-DEPLOY timer is disabled/inactive and the
   global `--all` timer is also disabled/inactive;
8. stop/disable the legacy pull timer, stop the pull service, then stop/disable
   the legacy web service;
9. require `hermes-blog` absent and `127.0.0.1:8089` unbound;
10. materialize only the exact reviewed Hermes Tech Compose;
11. invoke the exact-release adapter as `rozkalns-simple-deployer`;
12. require the new Compose service, `/health=200`, `/ready=200`, and a
    receipt binding the exact authorized source/digest;
13. enable/start only
    `rozkalns-simple-deployer@.timer` with instance `hermes-tech-public-rpi5`;
14. require the global `rozkalns-simple-deployer.timer` to remain
    disabled/inactive and verify the new runtime again.

The target-scoped timer is the standing ordinary release path after successful
activation. Enabling the global `--all` timer is forbidden because other
registered targets have independent activation state.

## Failure boundary

The first future installed-file creation is the first authorized mutation.
After that point, any error, timeout, identity drift, systemd ambiguity,
Compose/Docker failure, health regression, receipt mismatch or timer ambiguity
means evidence preservation and STOP.

There is no automatic retry, rollback, cleanup, restart, alternate image/tag,
alternate target or alternate shell path.

The cutover does not authorize database/schema/data mutation, protected
configuration or secret access, permissions outside the two fixed installed
files, Cloudflare/network mutation, package changes, or unrelated service,
timer or Docker lifecycle.

## Future owner gates

This source outcome still requires:

1. explicit merge of the exact Ready PR;
2. fresh exact-main CI after merge;
3. one later exact Composite LIVE authorization binding:
   - the then-current `RPi5_main` SHA;
   - `hermes-tech-public-rpi5`;
   - the exact Hermes Tech source SHA and immutable digest;
   - fixed operator installation plus the reviewed one-time cutover/timer
     activation mutation classes.

No source file, issue, PR or merge grants that LIVE authority.
