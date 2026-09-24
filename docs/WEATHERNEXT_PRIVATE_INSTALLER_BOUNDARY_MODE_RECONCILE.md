# WeatherNext installer-boundary restrictive-umask recovery

A fresh privileged read-only preflight after the merged installer-boundary refresh transport proved that the reviewed Git identities were exact, but the host's restrictive checkout umask materialized executable files as `0700` and non-executable files as `0600`. The existing bootstrap verifier requires canonical filesystem modes `0755` and `0644`, so the refresh must remain fail-closed until that mismatch is reconciled.

This source slice does **not** relax the bootstrap verifier and does not authorize host mutation. It defines a separate fixed recovery contract for exactly three already-reviewed files.

## Fixed recovery state

The classifier accepts only two complete states:

- `RESTRICTIVE`: all three fixed files have the reviewed restrictive-umask modes and exact owner/Git mode/blob/content identity;
- `EXACT`: all three have the canonical filesystem modes with the same reviewed identities.

Any mixed state, unexpected mode, ownership drift, symlink/hardlink drift, dirty Git state, wrong origin/head or wrong blob is `CONFLICT` and must STOP.

The three allowed transitions are:

1. runtime adapter `0700 -> 0755`;
2. runtime module `0600 -> 0644`;
3. stale trusted dispatch `0600 -> 0644`.

Only filesystem mode bits may change. Content, owner/group, paths and Git state must remain unchanged.

## Gate order

1. Merge this source through the normal owner merge gate and require exact-main CI.
2. Run a fresh exact-SHA privileged read-only preflight and require the complete `RESTRICTIVE` state.
3. Obtain a separate owner LIVE authorization for `rpi5.weathernext-private-installer-boundary.mode-reconcile.v1`, bounded to the three fixed mode mutations and no other host action.
4. Consume that authorization immediately before the first mode mutation. Any later error is STOP; no retry, cleanup or rollback.
5. Verify the complete `EXACT` state and unchanged Git/content/ownership identities.
6. Only then rerun the normal #700/#721 installer-boundary preflight. The actual `STALE -> EXACT` boundary refresh remains a different owner LIVE gate.

Source merge grants no LIVE authority. The public Weather runtime remains independent of this private WeatherNext recovery lane.
