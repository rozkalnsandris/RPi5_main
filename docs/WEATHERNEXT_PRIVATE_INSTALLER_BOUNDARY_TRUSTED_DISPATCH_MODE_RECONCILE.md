# WeatherNext trusted stale-dispatch mode reconcile

This source recovery replaces the stale three-file scope in PR #726 with the one prerequisite that still remains compatible with current source.

Fresh current-state evidence showed:

- current `RPi5_main/main` at recovery start: `f6834d0799b3f68e4f9f63833a3ea39272052e2c`;
- current bootstrap source intentionally accepts the manager-owned executable runtime at restrictive physical mode `0700` after #745;
- the manager-owned refresh runtime module is already canonical `0644` in fresh read-only host evidence;
- the installed current bootstrap still requires the fixed trusted stale dispatch to be root-owned, regular, one-link, exact reviewed blob `98218e3138f821390bece6dc10b770bd0b578cd9`, and physical mode `0644` before the separate #700/#721 refresh can proceed.

Therefore manager checkout mode normalization is no longer part of this recovery. In particular, this contract must not `chmod` or `chown` the manager checkout, runtime adapter, or runtime module.

## Fixed source contract

Operation:

`rpi5.weathernext-private-installer-boundary.trusted-dispatch-mode-reconcile.v1`

Target alias:

`rpi5-weathernext-private-installer-boundary-trusted-dispatch-mode-reconcile`

The only fixed file is:

`/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted/ops/lib/deploy_executor/weather_private_privileged_dispatch.py`

The trusted checkout must remain clean, detached, reviewed-origin, and exactly at reviewed stale head `79372e48ac53bf6d00142578b6543bc33a72a692`. The dispatch must be root-owned, regular, one-link, Git mode `100644`, and byte-identical to Git blob `98218e3138f821390bece6dc10b770bd0b578cd9`.

Accepted filesystem states are only:

- `0600`: recognized restrictive prestate, producing one future `0600 -> 0644` mode-only plan;
- `0644`: exact pre-consume no-op.

Every other mode or identity is conflict and must STOP before mutation.

## Mutation boundary

Source merge grants no LIVE authority. A future LIVE transaction, if still required after fresh privileged metadata-only preflight, may authorize at most one mutation category:

`filesystem.weathernext-private-installer-boundary-trusted-dispatch-mode-reconcile` — max 1.

That mutation may change only the fixed dispatch mode from `0600` to `0644`. Content, owner/group, path, Git state and all manager-checkout modes remain immutable. `rollback_policy=NONE`; automatic retry, cleanup and rollback are false.

After any future mutation starts, error or drift means evidence + STOP with no retry, cleanup, rollback or alternate path.

## Gate order

1. Merge this source only after the normal exact-head CI/review/mergeability gate and separate owner merge authorization.
2. Require fresh exact-main CI after merge.
3. Perform a separately authorized privileged metadata-only read-only preflight of the fixed trusted checkout and dispatch identity.
4. If the dispatch is already exact `0644`, treat it as a pre-consume no-op and do not create mutation authority merely to rewrite it.
5. If and only if the dispatch remains the recognized exact `0600` prestate, obtain a separate exact owner LIVE authorization for this one mode-only mutation.
6. Verify exact `0644` plus unchanged trusted Git/content/owner identity.
7. Only then resume a fresh #700/#721 installer-boundary preflight. The actual installer-boundary refresh remains a different owner LIVE gate.

This recovery performs no #700/#721 refresh, manager/trusted Git mutation, backend/private-runtime/application mutation, credential/protected-config access, Google/BigQuery/SQLite action, Docker/systemd/package/network/Cloudflare mutation, or repository-settings mutation.
