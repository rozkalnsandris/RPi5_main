# WeatherNext private installer boundary refresh

Status: **SOURCE READY / LIVE REFRESH SEPARATELY REQUIRED**  
Issue: `RPi5_main#700`  
Operation: `rpi5.weathernext-private-installer-boundary.refresh.v1`

## Purpose

This source slice closes the prerequisite identified after the fresh `rozkalns_weather#122`
preflight. The host already has the WeatherNext privileged installer boundary, but its trusted
source checkout can lag current reviewed `RPi5_main`. Source merge does not update that installed
boundary and does not authorize any host mutation.

The refresh contract is deliberately narrower than initial bootstrap. It applies only when both
the fixed trusted checkout and fixed installed entrypoint already exist in a mechanically
reviewable stale state.

## Fixed identities

- source repository: `rozkalnsandris/RPi5_main`
- reviewed origin: `https://github.com/rozkalnsandris/RPi5_main.git`
- manager resolver: `repo-owner-home/RPi5_main`
- trusted checkout: `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted`
- reviewed source entrypoint: `ops/bin/rpi5-weathernext-private-host-privileged-install`
- installed entrypoint: `/usr/local/sbin/rpi5-weathernext-private-host-privileged-install`
- target alias: `rpi5-weathernext-private-installer-boundary-refresh`
- rollback: `NONE`

No caller may select another repository, origin, checkout, path, command, argv or environment.

## State classification

The source planner classifies only four public-safe states.

`EXACT` means the trusted checkout is root-owned `0755`, clean, detached, correct-origin and at
the exact current-main SHA, and the installed entrypoint is root-owned `0755` and byte-exact to
the reviewed entrypoint blob. `EXACT` is a pre-consume no-op.

`STALE` is accepted only when the same structural checks pass, the trusted HEAD is a reviewed
ancestor of the exact current source, and both the trusted and installed entrypoint bytes exactly
match that reviewed stale HEAD. Stale but unreviewed or locally modified bytes are conflicts.

`ABSENT` is not a refresh case. The existing initial bootstrap remains the only valid path.

`CONFLICT` fails closed before authorization consume.

Current-main/source drift, failed exact-main CI, wrong manager origin or any manager
HEAD/index/worktree snapshot drift also fail before a refresh plan is emitted.

## Frozen future mutation envelope

A valid `STALE -> EXACT` future LIVE refresh contains exactly:

1. `git.weathernext-private-installer-checkout-fetch` — max 1. Fetch only reviewed `origin/main`;
   require the fetched ref equals the exact owner-authorized current-main SHA and leave manager
   HEAD/index/worktree unchanged.
2. `git.weathernext-private-installer-trusted-checkout-advance` — max 1. Advance only the fixed
   clean detached trusted checkout from its reviewed ancestor to the exact source SHA.
3. `filesystem.weathernext-private-installer-entrypoint-replace` — max 1. Replace only the fixed
   root-owned `0755` entrypoint after its preimage is proved byte-exact to the stale reviewed blob;
   require the postimage byte-exact to the exact-source reviewed blob.

The refresh contract does not allow `git clone`, reset, clean, pull, merge, rebase, force,
manager branch switching, wildcard `safe.directory`, Git configuration mutation or hidden
manager repair. It grants no generic root or shell authority.

Authorization is consumed immediately before the first future mutation. Any error, source/head
drift, conflicting fixed object or verification failure after that point is STOP. There is no
automatic retry, cleanup, rollback or alternate path.

## Explicit non-goals

The refresh cannot install the WeatherNext backend capability, stage the Weather application,
materialize the private Python runtime, read/create Google credentials, bind a Google project,
mutate an Analytics Hub link, issue a BigQuery request, or write SQLite/schema/corpus/snapshot
data. It also grants no Docker, systemd, package, network or Cloudflare mutation.

DWD remains the authoritative severe-weather warning source in Germany. WeatherNext remains
`primary_research` forecast output and is not an official warning source.

## Post-merge gate order

After this source outcome is merged and exact-main CI is green:

1. obtain a fresh sanitized read-only `rpi5` boundary preflight;
2. issue a separate exact owner LIVE authorization for this boundary refresh only;
3. execute the fixed stale-to-exact refresh once and verify exact checkout/entrypoint identity;
4. freshly reconcile backend-install source, Queue and LIVE eligibility;
5. install and verify `rpi5.weathernext-private-backend.v1` under its own authority;
6. establish private application/runtime/auth/project/link prerequisites only under their
   separately frozen gates;
7. resume `rozkalns_weather#122` read-only first access;
8. keep the production SQLite forecast snapshot behind its own later mutation gate.

The descriptor `ops/deploy/weather-private-installer-boundary-refresh.json` and
`weather_private_installer_boundary_refresh.py` are the machine-readable source contract.
