# Hermes Tech partial SIMPLE-DEPLOY resume v1

Issue: `#1451`  
Target: `hermes-tech-public-rpi5`  
Status: **SOURCE-ONLY / NOT AUTHORIZED / NOT EXECUTED**

## Root cause

The second one-time cutover attempt retired the legacy Hermes Tech runtime and
materialized the reviewed SIMPLE-DEPLOY Compose, then stopped at
`exact_reconcile_failed`.

Read-only decomposition proved the exact-release helper reached the pinned
generic deployer, verified the Compose and resolved the expected production
digest, then raised:

`TypeError: SimpleDeployer._inspect_image() got an unexpected keyword argument 'origin'`

The helper had been written against a newer source API than the exact installed
generic module it explicitly pins. The Hermes target never uses origin mode, so
the reviewed fix calls the pinned two-argument inspect API and explicitly rejects
origin mode.

## Reviewed partial baseline

The resume path accepts only the captured post-failure state:

- legacy web and pull timer disabled/inactive;
- legacy pull service static/inactive;
- no legacy Hermes container;
- exact reviewed Compose already present with SHA-256
  `fd1ca0d00c79bfb5e5cd1be589ae13b378c5c223be0b61d3f14f31da687fe6b9`;
- no SIMPLE-DEPLOY Hermes container;
- `127.0.0.1:8089` unbound;
- no success receipt;
- target-scoped Hermes SIMPLE-DEPLOY timer disabled/inactive;
- global all-target SIMPLE-DEPLOY timer disabled/inactive;
- stale status file exact SHA-256
  `42187d0258d92b4dfb644d8d2261a4dc604d77b81d542eb93d3637c5e681cf5d`.

Any drift blocks resume. This recovery never restarts the retired legacy runtime
and never rematerializes or removes the Compose.

## Helper recovery

The existing fixed installer gains
`helper-upgrade-check` / `helper-upgrade-apply`.

The recovery baseline is main
`1af1b450a0082894f405343505b6fb07606a26c1`, whose installed helper SHA-256
is `8a6cb72706c61dffd1c126c825169f92363edcbf328fb0bce42bdf60a014d050`.

A future separately authorized helper recovery may replace only:

`/usr/local/libexec/rozkalns-simple-deployer/hermes-tech-exact-reconcile-v1`

It requires the installed cutover operator to equal current-main source, stages
one fixed `O_EXCL|O_NOFOLLOW` file in the same root-owned directory, verifies
root:root mode `0555`, performs one atomic replace and fsyncs the directory.
There is no retry, rollback or cleanup path.

## Resume operator

The reviewed source entrypoint is:

`ops/bin/hermes-tech-simple-deploy-resume-v1`

A future separately authorized installer may create only:

`/usr/local/sbin/hermes-tech-simple-deploy-resume-v1`

as root:root mode `0500`.

The resume operator verifies exact current-main bytes for itself, the existing
cutover operator and the recovered helper. It then requires the exact partial
baseline above and revalidates the owner-authorized immutable Hermes Tech source
SHA and digest.

Its only forward mutations are:

1. invoke the fixed exact-release helper once;
2. verify the immutable container identity, `127.0.0.1:8089`, `/health=200`,
   `/ready=200` and exact success receipt;
3. enable/start only the target-scoped Hermes SIMPLE-DEPLOY timer;
4. verify the global all-target timer remains disabled/inactive;
5. verify the runtime again.

No legacy unit is started, enabled or modified. No Compose file is recreated or
removed. No global timer, database/data, secret, protected config, network,
Cloudflare or unrelated host mutation is in scope.

## Failure semantics

Helper replacement, resume installation and resume execution are separate
bounded mutation categories inside one future Composite LIVE envelope.

The first authorized mutation consumes that envelope. Any later error or
ambiguity preserves evidence and STOPs. There is no automatic retry, rollback,
cleanup, alternate image, alternate target, alternate shell path or legacy
restart.

Source merge alone performs no host mutation.
