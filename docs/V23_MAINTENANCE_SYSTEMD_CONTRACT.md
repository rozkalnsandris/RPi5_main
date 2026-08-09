# V23 RPi5 maintenance systemd scheduling contract

## Status

Repository-only implementation for issue #97. Production unchanged.

V23 replaces the legacy cron/@reboot activation model with supervised systemd oneshot services and calendar timers, while preserving the existing weekly/daily schedule intent and keeping production activation as a separately gated transaction.

The systemd design builds on the reviewed and merged V21 updater (#95 / PR #99) and V22 health components (#96 / PR #101). It does not install, enable, start, stop, reboot, remove cron or send notifications by itself.

## FHS continuity

V23 preserves the canonical helper installation boundary established by V21 and V22: `/usr/local/lib/rpi5-maintenance`.

The scheduler cutover operator installs and verifies all internal updater, health and Telegram helper files beneath that directory. The former `/usr/local/libexec/rpi5-maintenance` path is not part of the reviewed control plane and must not be reintroduced by scheduler installation or notification wrappers.

Administrator-facing executables remain under `/usr/local/sbin`.

## Why systemd

The 2026-08-09 incident demonstrated the failure mode of the legacy scheduler: cron invoked a missing home-directory executable, the command failed outside a supervised service state, local MTA delivery was unavailable, and there was no useful first-class job status.

V23 moves activation into normal service units so execution state, exit status and stdout/stderr are observable through `systemctl` and journald. Finite maintenance tasks use `Type=oneshot`.

## Units

### Weekly update

`rpi5-update.service`

- `Type=oneshot`;
- `ExecStart=/usr/local/sbin/rpi5-update`;
- `TimeoutStartSec=2h` so package/Hermes/Docker work is not killed by the normal short service timeout;
- ordered after `network-online.target` and `docker.service`, but does not `Requires=` Docker: if Docker is unexpectedly down the updater should observe/fail rather than silently starting it and hiding the fault;
- stdout/stderr goes to journald;
- `OnFailure=rpi5-maintenance-notify@%N.service` is a systemd-level fallback even if the updater fails before its own reporting path can run.

`rpi5-update.timer`

- `OnCalendar=Sun *-*-* 02:20:00`;
- `Persistent=true`;
- `RandomizedDelaySec=0`;
- `AccuracySec=1s`;
- explicitly activates `rpi5-update.service`.

`Persistent=true` means a calendar event missed while the timer was inactive may be triggered when the timer becomes active again. It does not retry a service that already ran and failed.

### Daily monitor

`rpi5-monitor.service`

- `Type=oneshot`;
- `ExecStart=/usr/local/sbin/rpi5-monitor`;
- `TimeoutStartSec=5min`;
- ordered after network-online/Docker/Cloudflared/SSH startup ordering;
- failure notification only; a successful daily health check is intentionally quiet.

`rpi5-monitor.timer`

- `OnCalendar=*-*-* 09:00:00`;
- `Persistent=false`;
- `RandomizedDelaySec=0`;
- `AccuracySec=1s`.

The monitor timer deliberately does not catch up a missed 09:00 run after boot because `rpi5-post-reboot.service` is the separate boot health path. This avoids immediate duplicate health checks after a late boot.

### Post reboot

`rpi5-post-reboot.service`

- `Type=oneshot`;
- boot-enabled via `WantedBy=multi-user.target`;
- ordered after network-online/Docker/Cloudflared/SSH;
- `TimeoutStartSec=7min`, covering the V22 bounded 30×10s readiness loop with margin;
- both `OnSuccess=` and `OnFailure=` invoke the notification template so every reviewed reboot gets a definitive health result.

The service does not use a guessed fixed boot sleep. Ordering and the bounded V22 readiness loop are separate concerns.

## Notification isolation

`rpi5-maintenance-notify@.service` is an isolated `DynamicUser=yes` oneshot notification service.

The update/monitor/post-reboot services receive no Telegram credentials. The notifier alone uses:

- `LoadCredential=telegram-token:/etc/credstore/rpi5-maintenance-telegram-token`;
- `LoadCredential=telegram-chat-id:/etc/credstore/rpi5-maintenance-telegram-chat-id`.

Systemd exposes loaded credentials to the service through `$CREDENTIALS_DIRECTORY`. The V22 Telegram transport at `/usr/local/lib/rpi5-maintenance/rpi5-maintenance-telegram.py` reads those files and message text from stdin.

The formatter uses the monitor metadata systemd passes to success/failure handlers (`MONITOR_UNIT`, `MONITOR_SERVICE_RESULT`, `MONITOR_EXIT_CODE`, `MONITOR_EXIT_STATUS`, `MONITOR_INVOCATION_ID`). This avoids parsing journal text to reconstruct the original service result.

The notification unit is hardened with a dynamic identity, empty capabilities, no-new-privileges, read-only system/home protection, private devices/tmp and an address-family allowlist. Notification failure has no `OnFailure=` recursion and cannot rewrite the triggering service result.

## Scheduler migration operator

Repository source: `ops/bin/rpi5-maintenance-systemd-cutover`.

The operator is intentionally phased.

### `--check`

Read-only migration preflight:

- verifies the root-only existing update configuration;
- derives the maintenance user's home from the account database rather than tracking it in Git;
- verifies exact active legacy cron entries;
- binds the current legacy updater to the reviewed 2026-08-09 v17 SHA256 baseline;
- validates both calendar expressions.

### `--inventory-candidate`

Prints currently running Docker container names as input for operator review. It does not create the V22 required-container inventory. Production must review the then-current active runtime and create `/etc/rpi5-maintenance/required-containers` explicitly before activation.

### `--install`

Installs reviewed V21/V22/V23 administrator executables under `/usr/local/sbin`, internal helpers under `/usr/local/lib/rpi5-maintenance`, and units under `/etc/systemd/system`. It copies the existing Telegram values from root-only update configuration into root-only `/etc/credstore` files, performs `systemctl daemon-reload`, `systemd-analyze verify`, and calendar parsing.

Crucially, `--install` does **not** enable or start any new unit or timer and does not remove cron. It therefore cannot create a double scheduler.

### `--activate --allow-persistent-catchup`

This is the no-double-trigger cutover transaction. The explicit catch-up flag is mandatory because first activation of a `Persistent=true` weekly timer may immediately run a missed Sunday calendar event.

Before cron is touched it requires:

- exact reviewed legacy cron baseline;
- exact reviewed legacy v17 updater SHA;
- installed system-owned targets/units;
- a non-empty root-controlled required-container inventory;
- root-controlled Telegram credential files;
- new timers not already enabled.

Then it:

1. creates verified `cp -a` rollback copies of the three legacy cron files under `/var/lib/rpi5-maintenance-scheduler/legacy-cron`;
2. removes the three legacy cron triggers;
3. enables post-reboot activation;
4. enables and starts the update/monitor timers;
5. verifies enablement/activity;
6. writes a root-only active marker.

The activation has an ERR rollback trap. If any step after cron retirement fails, new timers are disabled/stopped, post-reboot enablement is removed, and the exact cron copies are restored.

There is deliberately no automatic `systemctl start rpi5-update.service` preflight. Running the mutating weekly updater is a separate production decision.

### `--verify`

Requires:

- installed reviewed targets under the canonical `/usr/local/sbin` and `/usr/local/lib/rpi5-maintenance` roots;
- non-empty required-container inventory;
- all three legacy cron files absent;
- activation marker present;
- post-reboot unit enabled;
- update/monitor timers enabled and active.

It then displays both timers through `systemctl list-timers`.

### `--rollback`

Disables/stops the new timers, disables post-reboot boot activation, restores the exact backed-up legacy cron files, removes the active marker, reloads systemd and re-runs the legacy baseline preflight.

Rollback intentionally leaves the reviewed `/usr/local` files and unit files installed but inactive; scheduler state is restored without deleting recovery evidence.

## No-double-trigger invariant

At no successful activation point are both legacy cron triggers and active new timers retained:

- install phase leaves cron active and systemd inactive;
- activation removes/backups cron before enabling/starting timers;
- activation failure disables new scheduling before restoring cron;
- rollback disables new scheduling before restoring cron.

## Persistent timer safety

The mandatory `--allow-persistent-catchup` flag is an operator acknowledgement, not a way to force an update. Without it `--activate` exits before modifying cron or enablement.

This is necessary because the weekly timer intentionally uses `Persistent=true`; first activation after a missed Sunday 02:20 event can legitimately cause immediate activation.

## Observability

After activation:

```text
systemctl status rpi5-update.timer rpi5-monitor.timer
systemctl list-timers --all rpi5-update.timer rpi5-monitor.timer
systemctl status rpi5-update.service rpi5-monitor.service rpi5-post-reboot.service
journalctl -u rpi5-update.service
journalctl -u rpi5-monitor.service
journalctl -u rpi5-post-reboot.service
journalctl -u 'rpi5-maintenance-notify@*'
```

A failed oneshot remains a failed service result. `Persistent=true` does not transform that failure into a retry.

## Repository validation

V23 requires:

- `systemd-analyze calendar` parses both schedules;
- `systemd-analyze verify --root=... --recursive-errors=no` validates all six units against isolated CI stubs, without modifying the CI host;
- exact timer persistence/randomization/accuracy semantics are regression-tested;
- service timeouts and success/failure notification links are regression-tested;
- credentials appear only on the notification unit;
- cutover and notification sources require `/usr/local/lib/rpi5-maintenance` and reject the former `/usr/local/libexec/rpi5-maintenance` helper root;
- cutover source is public-safe and derives user-home state at runtime;
- install phase cannot enable/start units;
- activation ordering is statically tested: catch-up acknowledgement and preflight precede cron backup/removal, which precedes systemd enable/start;
- rollback ordering is tested: systemd disable/stop precedes cron restoration;
- no migration path starts the mutating update service directly;
- normal repository public-safety and full-history secret scans remain required.

## Production boundary

Merge does not authorize `--install`, `--activate`, a persistent catch-up run, creation of the required-container inventory, credential migration, cron removal, service/timer enablement, Telegram delivery, updater execution or host reboot. Production cutover remains an explicit later transaction in #123 with live preflight and rollback evidence.
