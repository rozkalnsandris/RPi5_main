# V22 RPi5 maintenance health privilege contract

## Status

Repository-only replacement design for issue #96. Production unchanged.

The deleted legacy `monitor.sh` and `post-reboot.sh` are not restored byte-for-byte. Their old model was internally inconsistent: an interactive-user cron entry executed code that sourced root-only maintenance secrets and attempted to write root-owned logs.

V22 replaces that model with three deliberately separated responsibilities:

1. `rpi5-monitor` performs read-only scheduled health evaluation and returns an authoritative exit status.
2. `rpi5-post-reboot` performs bounded post-boot readiness evaluation and returns an authoritative exit status.
3. `rpi5-maintenance-telegram.py` is a separate notification transport that reads Telegram credentials from the systemd credentials directory and message text from stdin.

Systemd unit/timer activation is owned by #97. V22 imports the executable components and fixes their privilege/configuration model without enabling, starting, stopping, rebooting or changing cron.

## FHS helper placement

V22 reuses the canonical helper root established by V21: `/usr/local/lib/rpi5-maintenance`. The former `/usr/local/libexec/rpi5-maintenance` path is not part of the reviewed maintenance control plane and must not be reintroduced by later stacked layers.

## Service identity decision

The health entrypoints are intended to run as a root-owned system service identity. This is deliberate rather than convenience:

- host-wide Docker inspection requires access to the Docker daemon socket, which is a privileged control surface;
- system service state is part of the health result;
- adding the interactive user to a broader Docker/secret-reading group would increase that user's standing privileges merely to preserve a legacy scheduler model.

The health entrypoints do **not** read Telegram credentials or `/etc/rpi-update.conf`. Root is used for host inspection, not as a reason to broaden secret access.

The notification transport is separable from the health process. #97 may run it with a narrower service identity and `LoadCredential=`/systemd credentials. Credential values are not accepted through command-line arguments or dedicated secret environment variables.

## Non-secret runtime inventory

Expected active containers are host state, not historical Git state. Both health entrypoints therefore read a root-controlled non-secret inventory from `/etc/rpi5-maintenance/required-containers`, one exact container name per line.

This solves two opposite failure modes:

- a completely missing required container is a failure even though it no longer appears in `docker ps -a`;
- an intentionally retained stopped/retired historical container does not create a false alarm merely because it still exists in Docker metadata.

Extra containers are ignored by the required-set comparison. The inventory itself must be a regular root-owned file and must not be group/world writable. Production migration must generate the initial list from the then-current reviewed active runtime, not blindly copy an older baseline.

## Logging contract

Stdout/stderr is the authoritative execution record and is intended for journald under the future systemd units. V22 does not create or append `/var/log/rpi5-monitor.log` or `/var/log/rpi5-post-reboot.log`.

This preserves the original process exit status as first-class service state instead of hiding it behind a successful `tee`/notification path. Notification failure is a separate result and must never rewrite a health failure into success.

## Monitor health model

`rpi5-monitor` is read-only and checks:

- `docker.service`, `ssh.service`, and `cloudflared.service` are active;
- Docker state is enumerated with `docker ps -a` using exact container name, state and health fields;
- every container named in the required-container inventory exists and is `running` with health absent/`none` or `healthy`;
- an empty required-container inventory is a failure;
- extra historical/retired containers do not affect the required-set result;
- CV and Hermes Tech loopback origins remain `127.0.0.1:8088` and `127.0.0.1:8089`;
- public service endpoints are checked independently so tunnel/public reachability is not inferred from container state alone.

A required container whose healthcheck is `starting` is not green in the daily monitor. The post-reboot flow has a bounded retry window specifically to allow startup convergence.

## Post-reboot model

`rpi5-post-reboot` does not implement boot ordering by sleeping for a guessed fixed delay. #97 must order the future service after the dependencies it actually requires, including Docker and configured networking.

After activation, the executable performs a bounded readiness loop. Each attempt requires:

- Docker, SSH and Cloudflared system services active;
- every explicitly required Docker container present, running and healthy/without a healthcheck;
- the two loopback application origins reachable;
- selected public CV/Hermes endpoints reachable.

The loop is bounded to 30 attempts with a 10-second retry delay. Exhaustion exits nonzero and emits final systemd/container diagnostics to journald.

## Telegram credential model

`rpi5-maintenance-telegram.py` expects a systemd-provided `$CREDENTIALS_DIRECTORY` containing:

- `telegram-token`
- `telegram-chat-id`

The message is read from stdin. Credential files must be regular, non-symlink files and non-empty. The notifier chunks long messages below Telegram's message limit and sanitizes transport errors so credential values are never written to stderr.

The notifier source contains no Telegram token/chat value, private home path, private IP or `/etc/rpi-update.conf` dependency.

## Public repository boundary

Tracked V22 source contains no concrete user-home path, private RFC1918 host address, Telegram token/chat identifier, legacy root-only configuration content or concrete host container inventory.

Public URLs are intentional service identities. Private and host-specific runtime values remain host state rather than Git state.

## Source-to-installed mapping

| Repository source | Future installed target | Owner/mode intent |
|---|---|---|
| `ops/bin/rpi5-monitor` | `/usr/local/sbin/rpi5-monitor` | `root:root`, `0750` |
| `ops/bin/rpi5-post-reboot` | `/usr/local/sbin/rpi5-post-reboot` | `root:root`, `0750` |
| `ops/lib/rpi5-maintenance-health.sh` | `/usr/local/lib/rpi5-maintenance/rpi5-maintenance-health.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-maintenance-telegram.py` | `/usr/local/lib/rpi5-maintenance/rpi5-maintenance-telegram.py` | `root:root`, not group/world writable |
| host inventory | `/etc/rpi5-maintenance/required-containers` | `root:root`, non-secret, not group/world writable |

#97 owns the actual systemd service/timer files, credential loading, dependency ordering and activation/cutover.

## Repository gates

- shell syntax for both entrypoints and shared health helper;
- Python compilation for notifier;
- deterministic container state/health classification tests;
- required-container set detects missing required services;
- extra retired/stopped containers do not create false alarms;
- empty required inventory fails;
- HTTP reachability classification tests;
- exact loopback-origin regression tests;
- both entrypoints require `/usr/local/lib/rpi5-maintenance` and reject the former `/usr/local/libexec/rpi5-maintenance` path;
- prohibition of `/etc/rpi-update.conf`, legacy file-log paths and Telegram secrets in health entrypoints;
- notifier credential-directory/symlink/empty-input tests;
- prohibition of dedicated Telegram secret environment variable names in notifier source;
- repository-wide public safety and full-history secret scan.

## Production boundary

Merge does not authorize installing these files, creating the required-container inventory, changing `/etc` permissions, enabling systemd units/timers, removing cron entries, restarting services, running post-reboot verification, rebooting the host or sending Telegram messages.
