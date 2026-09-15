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

Fresh read-only #557 host evidence selected `/home/andris/RPi5_main` as the only compatible existing operator-owned manager checkout. Its reviewed origin is exactly `https://github.com/rozkalnsandris/RPi5_main.git`.

The WeatherNext bootstrap uses that checkout only as Git object/remote source. A stale, detached or dirty manager worktree is not content authority. Git reads and `fetch` run as the repository owner. The manager worktree/index/HEAD are snapshotted and must remain unchanged. No clone, reset, clean, switch, pull, merge, rebase, wildcard `safe.directory` or Git config trust widening is permitted.

The only root Git action is the fixed detached `worktree add` needed to create `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted` below the root-owned deploy-state parent.

## WeatherNext mutation envelope

Immediately before authorization consume, the engine revalidates the human owner LIVE-AUTH, READY queue, exact current `RPi5_main/main`, required exact-main `validate` CI, reviewed ancestry, manager origin, remote `main`, replay marker availability and target prestate.

An exact already-installed state is a read-only no-op and does not consume authorization. Otherwise the durable consume marker is the first mutation boundary. After consume the maximum operation set is exactly:

1. one `git.weathernext-private-installer-checkout-fetch`;
2. one `git.weathernext-private-installer-checkout-worktree-add`;
3. one `filesystem.weathernext-private-installer-entrypoint-install`.

The trusted checkout is fixed at `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted`. The installed entrypoint is fixed at `/usr/local/sbin/rpi5-weathernext-private-host-privileged-install`, `root:root 0755`, with bytes required to equal the exact reviewed Git object.

If anything fails after consume, the engine emits bounded sanitized evidence and stops. Automatic retry, cleanup, worktree removal/prune, rollback and alternate mutation are forbidden.

## Post-merge V12 engine-upgrade LIVE gate

The source outcome deliberately does not install the new engine. Because the existing `/home/andris/RPi5_main` manager checkout may be stale/detached/dirty, the later owner-authorized engine-upgrade gate stages reviewed source without repairing that worktree.

Before its first mutation, bind one exact merged current `main` SHA and verify the reviewed origin and exact-SHA CI. Then the bounded source-staging sequence is:

1. `git -C /home/andris/RPi5_main fetch --no-tags origin refs/heads/main:refs/remotes/origin/main`;
2. verify `refs/remotes/origin/main` equals the authorized merged SHA;
3. require the manager worktree/index/HEAD snapshot to be unchanged and require local `main` not to be checked out by another worktree;
4. `git -C /home/andris/RPi5_main update-ref refs/heads/main <exact-merged-main-sha>`;
5. `git -C /home/andris/RPi5_main worktree add /home/andris/RPi5_main-v12-engine-trusted refs/heads/main`;
6. verify the trusted engine-source worktree is clean `main` at the exact SHA;
7. run `bash /home/andris/RPi5_main-v12-engine-trusted/scripts/rpi5-deploy install-engine --confirm <12-character-exact-merged-main-sha>`;
8. run `bash /home/andris/RPi5_main-v12-engine-trusted/scripts/rpi5-deploy engine-status` and require the exact release SHA plus the WeatherNext capability descriptor.

That is one separately authorized LIVE gate. It does not execute `rpi5.weathernext-private-installer-boundary.install.v1`. Failure is fail-closed; there is no automatic retry, cleanup or rollback.

After successful sanitized engine verification, the host state is `HOST_V12_WEATHERNEXT_BOOTSTRAP_CAPABILITY_INSTALLED` and `RPi5_main#556` can resume against the installed boundary. The subsequent WeatherNext bootstrap, private backend install, application/runtime work, Google/Analytics Hub/BigQuery work and SQLite snapshot each remain separate authorization/gating concerns.

DWD remains the authoritative severe-weather warning source. WeatherNext remains `primary_research` and is not an official warning source.
