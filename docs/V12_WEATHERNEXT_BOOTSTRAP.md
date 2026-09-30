# V12 WeatherNext private-installer bootstrap

Issue `RPi5_main#557` extends the existing V12 root-isolated deploy engine with exactly one capability-specific operation:

- operation: `rpi5.weathernext-private-installer-boundary.install.v1`;
- target: `rpi5-weathernext-private-installer-boundary`;
- controller command: `bash ./scripts/rpi5-deploy weather-private-installer-bootstrap --authorization-issue-number <issue>`;
- caller-controlled input: the LIVE-AUTH issue number only.

This is not a generic dispatcher. Command, repository, source SHA, target, path, argv, environment, ownership, mode, mutation order and rollback policy are fixed in reviewed engine source.

## Source-ready state

Merging #557 establishes `SOURCE_READY_V12_ENGINE_UPGRADE_REQUIRED`. A source merge does not update `/usr/local/sbin/rpi5-deploy`, does not execute the WeatherNext operation and grants no LIVE authority.

`rpi5_weathernext_bootstrap.py` is part of the same versioned V12 engine source and installed-file inventory as `rpi5_deploy.py`. `install-engine` stages and hashes it into `/usr/local/libexec/rpi5-deploy/releases/<sha>/` as `root:root 0400`; the existing root-owned `env -i` wrapper remains the only privileged transport.

The ordinary V12 five-target backup/maintenance manifest is unchanged. `plan`, `deploy` and `rollback` never dispatch the WeatherNext operation. WeatherNext uses its own one-shot authorization and `rollback_policy=NONE` path.

## Fixed manager provenance

Fresh read-only #557 host evidence selected the repository owner's fixed `RPi5_main` checkout, resolved at runtime as `repo-owner-home/RPi5_main`, as the only compatible existing manager checkout. Its reviewed origin is exactly `https://github.com/rozkalnsandris/RPi5_main.git`.

The WeatherNext bootstrap uses that checkout only as Git object/remote source. A stale, detached or dirty manager worktree is not content authority. Git reads and the single allowed `fetch` run as the repository owner. The manager worktree/index/HEAD are snapshotted and must remain unchanged. No clone, reset, clean, switch, pull, merge, rebase, branch-ref repair, wildcard `safe.directory` or Git config trust widening is permitted.

The only root Git action in the WeatherNext bootstrap is the fixed detached `worktree add` needed to create `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted` below the root-owned deploy-state parent.

Exact entrypoint bytes are bound by Git blob identity. The engine compares the trusted checkout file's `git hash-object --no-filters` identity with the exact `<authorized-sha>:ops/bin/rpi5-weathernext-private-host-privileged-install` Git object, then installs `read_bytes()` from that verified checkout. Text-mode `git show` output is not used, so a trailing newline cannot be lost.

## WeatherNext pre-consume boundary

The WeatherNext command requires the already-installed V12 state directory and `deploy.lock` to exist with exact root-owned metadata. It opens that fixed lock without `O_CREAT`; lock acquisition is a kernel-only concurrency guard and does not create persistent state.

Immediately before authorization consume, the engine revalidates the human owner LIVE-AUTH, READY queue, exact current `RPi5_main/main`, required exact-main `validate` CI, reviewed ancestry, manager origin, remote `main`, replay-marker availability and target prestate.

The generic V12 command-failure logger is deliberately not used for this strict WeatherNext subcommand. Therefore a failure before authorization consume does not create a root log entry or other persistent state.

An exact already-installed state is a read-only no-op and does not consume authorization. Otherwise the durable consume marker is the first persistent mutation boundary. After consume the maximum operation set is exactly:

1. one `git.weathernext-private-installer-checkout-fetch`;
2. one `git.weathernext-private-installer-checkout-worktree-add`;
3. one `filesystem.weathernext-private-installer-entrypoint-install`.

The trusted checkout is fixed at `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted`. The installed entrypoint is fixed at `/usr/local/sbin/rpi5-weathernext-private-host-privileged-install`, `root:root 0755`, with bytes required to equal the exact reviewed Git object.

If anything fails after consume, the capability writes only bounded sanitized STOP evidence and stops. Automatic retry, cleanup, worktree removal/prune, rollback and alternate mutation are forbidden.

## Post-merge V12 engine-upgrade LIVE gate

The source outcome deliberately does not install the new engine. Because the existing manager checkout may be stale, detached or dirty, the later separately owner-authorized engine-upgrade gate stages reviewed source without repairing that worktree or mutating a local branch ref.

Before its first mutation, the gate binds one exact merged current `main` SHA, verifies the reviewed origin, verifies exact-SHA CI and records the current installed V12 wrapper/release baseline. The source-staging sequence is fixed:

1. resolve `repo-owner-home/RPi5_main`, verify the reviewed origin and snapshot its worktree/index/HEAD;
2. as the repository owner, run `git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main`;
3. require `refs/remotes/origin/main` to equal the authorized merged SHA and require the manager snapshot to remain unchanged;
4. as the repository owner, run `git worktree add --detach <repo-owner-home>/RPi5_main-v12-engine-trusted <exact-merged-main-sha>`;
5. require that trusted engine-source checkout to be clean, detached, at the exact SHA and to have the reviewed origin;
6. run `bash <repo-owner-home>/RPi5_main-v12-engine-trusted/scripts/rpi5-deploy install-engine --confirm <12-character-exact-merged-main-sha>`;
7. as part of that same engine-upgrade mutation class, require or initialize exact root-owned V12 control state `/var/lib/rpi5-deploy` mode `0700` and `/var/lib/rpi5-deploy/deploy.lock` mode `0600`; conflicting existing metadata fails closed;
8. run `bash <repo-owner-home>/RPi5_main-v12-engine-trusted/scripts/rpi5-deploy engine-status` and require the exact release SHA plus `HOST_V12_WEATHERNEXT_BOOTSTRAP_CAPABILITY_INSTALLED`.

`install-engine` accepts only a clean reviewed `main` checkout or a clean detached checkout whose `HEAD` equals freshly fetched `origin/main`; no arbitrary branch is accepted. The engine upgrade does not execute `rpi5.weathernext-private-installer-boundary.install.v1`.

That engine update is one separately authorized LIVE gate. Source merge alone never authorizes it. Failure is fail-closed; there is no automatic retry, cleanup or rollback.

After successful sanitized engine verification, `RPi5_main#556` can resume against the installed V12 transport. The subsequent WeatherNext bootstrap, private backend install, application/runtime work, Google/Analytics Hub/BigQuery work and SQLite snapshot each remain separate authorization/gating concerns.

DWD remains the authoritative severe-weather warning source. WeatherNext remains `primary_research` and is not an official warning source.
