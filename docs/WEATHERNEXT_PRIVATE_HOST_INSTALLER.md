# WeatherNext private host privileged installer

Status: **SOURCE READY / PRIVILEGED BOUNDARY HOST BOOTSTRAP REQUIRED**  
Issue: `RPi5_main#554`  
Capability install operation: `rpi5.weathernext-private-backend.install.v1`

## Purpose

This source slice closes the code-side transport gap after `RPi5_main#552` / PR `#553`. It gives the WeatherNext private host capability a capability-specific privileged installer that can consume one canonical owner LIVE-AUTH identity, revalidate GitHub/source/CI/replay state, derive the existing #552 install plan, and execute only that plan.

It does **not** install or activate anything on `rpi5`. Source merge grants no LIVE authority.

## Caller and authorization boundary

The installed privileged entrypoint accepts exactly one caller-controlled value:

`--issue-number <positive LIVE-AUTH issue number>`

The runtime independently revalidates:

- owner-authored, non-App `rozkalns.live-auth.v1` authority;
- READY Queue binding;
- operation `rpi5.weathernext-private-backend.install.v1`;
- target `rpi5-weathernext-private-backend-install`;
- exact current `RPi5_main/main` SHA and required `validate.yml` success;
- reviewed ancestry from `1fa9ace14aa8b0b7c3c46ac465f1a5093d35d0a7`;
- identical authorization refetch;
- durable one-shot replay availability;
- fixed sanitized checkout/operator/activation-marker state immediately before consume.

The caller cannot provide a command, executable, path, argv, environment, repository, source SHA, target, mutation plan, Google identity, credential, SQL or WeatherNext value.

## Capability install budget

The installer reuses `build_host_install_plan()` from #552. The only capability mutations are, in order and at most once each:

1. `git.weathernext-private-host-checkout-fetch`;
2. `git.weathernext-private-host-checkout-worktree-add`;
3. `filesystem.weathernext-private-host-operator-install`;
4. `filesystem.weathernext-private-host-activation-marker-write`.

Fixed targets remain:

- manager checkout: `/var/lib/rpi5-deploy/RPi5_main`;
- capability trusted checkout: `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-host-trusted`;
- installed capability operator: `/usr/local/sbin/rpi5-weathernext-private-host`;
- activation marker: `/var/lib/rpi5-deploy/weather-private-host/capability.json`.

The checkout and operator are root-owned mode `0755`; the marker is root-owned mode `0644`. The operator and marker use no-follow and no-overwrite semantics. A conflicting existing object is STOP, never overwrite/repair.

The marker-write category may create only its fixed parent directory when absent; that directory creation is part of the single fixed marker-publication operation and cannot be caller-selected.

## Consumption and failure semantics

A fully exact already-installed state is a read-only no-op and does not consume LIVE-AUTH. Otherwise durable authorization consumption happens immediately before the first mutation.

After consume, any Git/source/CI/replay drift, checkout conflict, write failure or verification failure stops execution. `rollback_policy=NONE`; there is no automatic retry, cleanup, worktree removal/prune, rollback, credential substitution or alternate route.

## Privileged-boundary bootstrap

The root-side entrypoint source is:

`ops/bin/rpi5-weathernext-private-host-privileged-install`

It is Git mode `100755` and is intended to run only from the fixed root-owned trusted source checkout:

`/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted`

A later host bootstrap may install it only at:

`/usr/local/sbin/rpi5-weathernext-private-host-privileged-install`

That boundary is deliberately **not installed by this source merge**. The bounded future bootstrap identity is `rpi5.weathernext-private-installer-boundary.install.v1` with exactly one checkout fetch, one detached worktree add and one entrypoint install; rollback remains `NONE`.

The conversational agent still receives no `sudo`, generic root shell or arbitrary command authority. If the trusted host lacks a reviewed mechanism capable of performing this bootstrap, the bootstrap itself is the next explicit owner LIVE gate; source must not fake `privileged_boundary_installed=true`.

## Post-install verification

A successful capability install must prove all three identities exact:

- trusted checkout is root-owned `0755`, exact authorized SHA, detached, clean and reviewed origin;
- `/usr/local/sbin/rpi5-weathernext-private-host` equals the reviewed source bytes and is root-owned `0755`;
- activation marker is the exact #552 schema/source identity and root-owned `0644`.

The installer does not stage the Weather application, materialize the private cp313 runtime, read/create Google credentials, bind a project, create an Analytics Hub link, issue BigQuery requests or write SQLite.

## Gate order after merge

1. exact-main source/CI verification for #554;
2. separately owner-authorized privileged-boundary bootstrap on `rpi5` if still absent;
3. sanitized read-only verification of that boundary;
4. separately owner-authorized `rpi5.weathernext-private-backend.install.v1` capability install;
5. sanitized exact capability verification;
6. only then establish separately frozen application/runtime/auth/project/link prerequisites where absent;
7. `rozkalns_weather#122` remains the later read-only WeatherNext first-access gate;
8. production SQLite snapshot remains a separate later mutation gate.

DWD remains the authoritative severe-weather warning source in Germany. WeatherNext remains `primary_research` forecast output and is not an official warning source.
