# WeatherNext private application staging

Status: **SOURCE READY AFTER #702 MERGE / LIVE DISABLED BY DEFAULT**  
Issue: `RPi5_main#702`  
Operation: `rpi5.weathernext-private-application-stage.v1`

## Purpose

This capability closes only the Weather application-staging prerequisite before WeatherNext private runtime and Google/BigQuery access. It does not stage anything by source merge and does not authorize any host mutation.

The operation has one caller-controlled field: the owner LIVE-AUTH issue number. The privileged entrypoint reads the canonical authorization issue and dispatches only between the pre-existing backend-install operation and this fixed application-stage operation. The caller cannot choose an operation, repository, source SHA, path, command, argv, environment, project, dataset, credential or SQL/query.

## Fixed identities

- source repository: `rozkalnsandris/rozkalns_weather`
- reviewed origin: `https://github.com/rozkalnsandris/rozkalns_weather.git`
- stage identity: `rozkalns-weather.weathernext-private-application-stage.v1`
- stage root: `/var/lib/rpi5-deploy/weather-private-application`
- public-safe marker: `/var/lib/rpi5-deploy/weather-private-application/source-stage.json`
- target alias: `rpi5-weathernext-private-application-stage`
- rollback policy: `NONE`

The source SHA comes only from the canonical owner authorization and READY Queue binding. JIT revalidation requires that SHA to remain exact current Weather `main` with required exact-SHA CI. It also requires the installed privileged installer boundary to be the clean detached reviewed-origin checkout at exact current `RPi5_main/main`.

## State model

The fixed stage has three states:

- `ABSENT`: the fixed final root and its deterministic partial root are absent; a bounded stage plan may be authorized later.
- `EXACT`: the fixed root is root-owned mode `0755`, the marker is root-owned mode `0644` with the exact four-key public-safe schema, Git origin is reviewed, HEAD is the exact authorized Weather SHA, checkout is detached and tracked files are clean. This is a deterministic no-op and does not consume an authorization because no production mutation starts.
- `CONFLICT`: any partial residue, wrong origin/SHA/metadata/marker, attached checkout or tracked drift. This fails closed. There is no implicit cleanup, overwrite, retry or repair.

The marker shape is intentionally identical to the already-reviewed `weather_private_bigquery_host_bindings.py` application-stage observer. Therefore the installed private backend can recognize the separately staged exact Weather source without silently performing staging during `rozkalns_weather#122`.

## Frozen mutation budget

A later explicitly authorized LIVE execution may perform only:

1. `git.weathernext-private-application-stage-clone-checkout` — max 1 composite fixed-origin clone/exact detached checkout primitive;
2. `filesystem.weathernext-private-application-stage-marker-write` — max 1;
3. `filesystem.weathernext-private-application-stage-publish` — max 1 no-replace publication.

Authorization is consumed immediately before the first authorized mutation. If anything fails after consume, the durable request stays consumed/failed-closed and the partial state is left for sanitized read-only evidence. No automatic retry, cleanup or rollback is performed.

This mutation envelope cannot materialize the private cp313 runtime, bind Google auth/project, mutate Analytics Hub, issue BigQuery requests, write SQLite/corpus data, mutate Docker/systemd/packages/network/Cloudflare, or expose generic root/shell authority.

## Post-merge sequence

Source merge alone changes no host state. The required order after exact-main CI is:

1. fresh sanitized read-only RPi5 preflight;
2. if the installed WeatherNext privileged installer boundary is stale, separately authorize and execute the already-reviewed installer-boundary refresh to the exact merged `RPi5_main` SHA;
3. create a fresh READY Queue entry for `rpi5.weathernext-private-application-stage.v1` bound to exact current Weather source;
4. create a fresh human-owner non-App LIVE-AUTH with the exact Queue/source/baseline/mutation-budget contract;
5. execute the fixed privileged entrypoint once with only `--issue-number` and verify the stage is `EXACT`;
6. separately establish the reviewed private cp313 runtime if absent;
7. separately establish Google auth, Google project and approved Analytics Hub linked-dataset bindings;
8. only then resume `rozkalns_weather#122` read-only first access;
9. production SQLite snapshot remains a later separate mutation gate.

DWD remains the authoritative severe-weather warning source in Germany. WeatherNext remains `primary_research`; no WeatherNext output from this capability is an official warning.
