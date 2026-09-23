# WeatherNext private backend manager-provenance recovery

Issue `RPi5_main#695` recovers the source-only manager-provenance mismatch exposed by the first owner-authorized `rpi5.weathernext-private-backend.install.v1` attempt.

## Incident boundary

The failed request was bound to:

- LIVE-AUTH `rozkalnsandris/deploy-authorizations#34`;
- READY queue `rozkalnsandris/ops-workflows#101`;
- source `RPi5_main@55d5ccbf01118bb3737e4e3f45dec5972a0e6b1f`;
- target `rpi5-weathernext-private-backend-install`;
- rollback policy `NONE`.

The canonical privileged installer was invoked once. It stopped because the backend source required `/var/lib/rpi5-deploy/RPi5_main`, which is not part of the reviewed host baseline. The entrypoint reported `production_mutation_started=unknown_after_boundary_entry`, so authorization #34 is consumed/failed and must never be reused. No retry, cleanup or rollback is part of this recovery.

## Correct manager provenance

The backend capability install now uses the same manager provenance model already reviewed for the V12 WeatherNext installer boundary:

`repo-owner-home/RPi5_main`

The running privileged installer derives the Git common directory from its fixed trusted installer source checkout, requires that common Git directory to belong to one non-root repository owner, and requires the manager checkout to equal that account's home plus `RPi5_main`. The reviewed origin remains exactly:

`https://github.com/rozkalnsandris/RPi5_main.git`

The manager checkout is Git object/remote provenance only. Its checked-out content is never install content authority. A stale or dirty manager is allowed, but its HEAD plus worktree/index status are snapshotted before the install plan and must remain unchanged through the operation.

The single allowed manager `fetch` runs as the repository owner with command-scoped `safe.directory`, system Git configuration disabled, the repository owner's existing global Git configuration available read-only for its credential helper, and a fixed refspec for `origin/main`. The installer does not mutate Git configuration and does not widen trust. The detached trusted worktree add remains the only root-side manager Git mutation because the destination lives below the root-owned deploy-state boundary.

There is no clone, reset, clean, pull, merge, rebase, switch, manager checkout creation, wildcard `safe.directory`, Git configuration mutation, or generic Git trust widening. Missing or incompatible provenance fails during pre-consume observation.

## Preserved backend install envelope

The recovery does not add a mutation class. The backend install budget remains exactly:

1. `git.weathernext-private-host-checkout-fetch` — max 1;
2. `git.weathernext-private-host-checkout-worktree-add` — max 1;
3. `filesystem.weathernext-private-host-operator-install` — max 1;
4. `filesystem.weathernext-private-host-activation-marker-write` — max 1.

Fixed targets remain unchanged:

- trusted checkout: `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-host-trusted`;
- operator: `/usr/local/sbin/rpi5-weathernext-private-host`;
- activation marker: `/var/lib/rpi5-deploy/weather-private-host/capability.json`.

`rollback_policy=NONE`, no-overwrite/no-follow semantics, one-shot authorization consumption, and no automatic retry/cleanup/rollback remain unchanged.

## Post-merge continuation

The old queue #101 is historical eligibility for the pre-fix source and is not reusable authority after the source SHA changes.

The installed privileged entrypoint `/usr/local/sbin/rpi5-weathernext-private-host-privileged-install` imports its backend implementation from the fixed trusted installer checkout `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted`. Therefore merging #695 does **not** by itself make the new backend source live on the host. The existing bootstrap contract is no-overwrite/no-cleanup and must not be reused as an implicit upgrade path.

After this recovery merges and exact-main CI is green:

1. perform a fresh sanitized read-only host preflight that records the installed privileged-installer trusted-checkout source identity and entrypoint identity;
2. if that installed boundary is not already exact to the new merged `RPi5_main/main` source, treat the state as `SOURCE_PREREQUISITE_REQUIRED` and define/review a separate bounded installer-boundary upgrade/rebind path; do not create a backend READY queue or LIVE-AUTH yet;
3. only after that separate source outcome is merged, separately owner-authorized on `rpi5`, and sanitized verification proves the privileged-installer boundary is exact to the required source, create/reconcile a READY queue bound to the then-current exact `RPi5_main/main` SHA;
4. create a fresh human-owner, non-App LIVE-AUTH;
5. execute `rpi5.weathernext-private-backend.install.v1` once under that new envelope and verify only the sanitized fixed capability postconditions.

`deploy-authorizations#34` remains consumed/failed and is never reusable. Google authentication/project binding, Analytics Hub/BigQuery first access, `rozkalns_weather#122`, and any SQLite snapshot remain later separate gates.

DWD remains the authoritative severe-weather warning source. WeatherNext remains `primary_research` and is not an official warning source.
