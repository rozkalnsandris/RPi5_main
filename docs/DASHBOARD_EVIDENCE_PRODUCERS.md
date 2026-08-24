# Dashboard sanitized evidence producers

## Purpose

This source contract supplies the narrow root-owned producer side required by
`rozkalnsandris/dashboard_RPi5#196`. It deliberately avoids giving the
Internet-facing dashboard chain broad journal, `video`, or Docker authority.

The data flow is:

```text
existing authoritative root jobs / fixed read-only probes
  -> rpi5-dashboard-evidence + dashboard-evidence.py
  -> /var/lib/dashboard-rpi5/evidence/*.json
  -> dashboard-rpi5-agent bounded O_NOFOLLOW readers
  -> normalized browser-safe API
```

This repository owns the producer boundary. `dashboard_RPi5` owns the consumer
schemas and browser normalization.

## Fixed evidence files

All live files are below `/var/lib/dashboard-rpi5/evidence`, are regular files,
root-owned, mode `0644`, no larger than 64 KiB, and are atomically replaced in
the same directory.

| File | Producer | Browser-safe content |
|---|---|---|
| `backups.json` | `rpi5-backup-serialized` best-effort receipt | run id, UTC start/end, result, duration, encrypted archive size, exit code |
| `endpoints.json` | `rpi5-dashboard-evidence` | transition id, curated endpoint id/label, state, HTTP code, latency |
| `maintenance.json` | `rpi5-dashboard-evidence` | systemd invocation id, actual execution exit time, bounded unit result |
| `deployments.json` | `rpi5-dashboard-evidence` via controlled-deploy state | latest successful `RPi5_main` transaction id, 12-char commit, completion time |
| `throttle.json` | `rpi5-dashboard-evidence` | observation time and Raspberry Pi `get_throttled` hex value |

Raw logs, response bodies, private paths, backup names, rclone remotes,
credentials, configuration contents, command text and terminal material are not
part of these files.

## Endpoint curation

Dashboard Phase 6B fails closed above eight distinct endpoint IDs. The producer
therefore curates exactly eight high-value public endpoints already present in
the authoritative host monitor: CV, Hermes Tech, Portainer, Grafana, Home
Assistant, AdGuard, Uptime Kuma and Hermes.

Prometheus is intentionally not duplicated in `endpoints.json`; the dashboard
already owns a dedicated Prometheus history/readiness path. The collector uses
the existing RPi5 reachability semantics: HTTP 2xx/3xx/401/403 is `UP`, another
valid HTTP response is `DEGRADED`, and no valid HTTP response is `DOWN`.

Only transitions are retained, newest first, up to 64 events.

## Maintenance evidence

The dashboard must not receive broad journal authority merely to learn whether
the weekly updater completed. The collector uses fixed
`systemctl show rpi5-update.service` properties only:

- `ActiveState`;
- `InvocationID`;
- `Result`;
- `ExecMainExitTimestamp`.

Active/transitional executions are not recorded. A completed valid invocation
is keyed by its 32-hex `InvocationID`; `Result=success` becomes dashboard
`SUCCESS`, while another bounded systemd result becomes `FAILED` with the
bounded unit result token. `occurredAt` is derived from the unit's actual
`ExecMainExitTimestamp`, not from the later evidence-collector run.

The writer permits one narrow repair case for already-retained evidence: if the
same invocation has the same result/unit-result but the timestamp differs, the
record is replaced with the authoritative exit timestamp and the bounded event
list is re-sorted. A conflicting result for the same invocation fails closed.
This allows the pre-fix collector-time timestamp to self-heal without erasing a
real historical failure.

## Backup evidence

The reviewed V10/V12 backup core remains byte-identical and unchanged. The
serialization wrapper records evidence only after the core returns. Successful
size evidence comes from metadata of a newly written fixed-pattern encrypted
archive under the already reviewed `/opt/backups` directory; it does not read
the backup configuration or raw root-only log.

Evidence is best-effort: missing helper, missing safe size metadata, or an
evidence-write failure emits only a warning and never changes the authoritative
backup core exit code.

## Throttle evidence

The root collector may read only the fixed Raspberry Pi firmware command
`/usr/bin/vcgencmd get_throttled`. Its source-only systemd unit grants only the
fixed `/dev/vcio` device through `DevicePolicy=closed` and
`DeviceAllow=/dev/vcio rw`; it does not add the dashboard agent to the `video`
group. If the firmware command is unavailable or malformed, no fresh throttle
file is fabricated and the dashboard remains `UNAVAILABLE` once retained
evidence becomes stale.

## Deployment evidence

Phase 6C compares the proven production commit for
`rozkalnsandris/RPi5_main` with that repository's GitHub `main`. Therefore a
dashboard application release SHA is not valid deployment evidence for this
surface.

The collector derives `deployments.json` only from the fixed root-owned
controlled-deploy state below `/var/lib/rpi5-deploy`:

- `latest-success` selects one transaction;
- the transaction id must embed the same 12-char commit prefix;
- `transactions/<id>/transaction.json` must use schema
  `rpi5.controlled-deploy-transaction.v1`;
- repository must be exactly `rozkalnsandris/RPi5_main`;
- status must be exactly `success`;
- the full 40-char commit must match the id prefix;
- the controlled-deploy completion timestamp must be UTC and is normalized to
  canonical browser evidence format.

Only the latest authoritative successful transaction is projected. No target
paths, before/after fingerprints, private state paths, logs or rollback material
are copied to browser evidence. If the controlled-deploy state is absent or
invalid, the sync fails closed rather than retaining or inventing a dashboard
release as an `RPi5_main` deployment.

The legacy bounded `deploy-record` helper remains for compatibility with already
reviewed callers, but normal periodic production collection uses `deploy-sync`.
A dashboard rollout must never call `deploy-record` with a dashboard release
SHA to satisfy Phase 6C.

## Source-to-installed mapping

| Repository source | Future installed target |
|---|---|
| `ops/lib/dashboard-evidence.py` | `/usr/local/lib/rpi5-maintenance/dashboard-evidence.py` |
| `ops/bin/rpi5-dashboard-evidence` | `/usr/local/sbin/rpi5-dashboard-evidence` |
| `ops/systemd/rpi5-dashboard-evidence.service` | `/etc/systemd/system/rpi5-dashboard-evidence.service` |
| `ops/systemd/rpi5-dashboard-evidence.timer` | `/etc/systemd/system/rpi5-dashboard-evidence.timer` |
| `ops/bin/rpi5-backup-serialized` | existing reviewed serialized backup entrypoint, exact live target to be revalidated before deployment |

## Validation

`make validate` covers the pure producer functions, file bounds, deduplication,
maintenance timestamp repair/conflict refusal, authoritative controlled-deploy
projection, malformed retained evidence, exact eight-endpoint curation, shell
syntax, backup-result preservation assertions and the source-only systemd
least-privilege shape.

## Production boundary

This document and its source PR perform no installation or activation.
Repository merge alone does not authorize:

- replacing the live backup wrapper;
- installing or replacing the evidence helper/collector;
- creating or changing `/var/lib/dashboard-rpi5/evidence`;
- installing/enabling/starting/restarting the evidence service or timer;
- `/dev/vcio` device-policy activation;
- any identity/group change;
- any Docker, Cloudflare, network or dashboard deployment mutation;
- executing a backup/update/deploy;
- changing `/var/lib/rpi5-deploy` controlled-deploy state.

Any live correction remains a separately owner-authorized exact-SHA operation.
It must preserve the existing trust boundaries and stop on the first post-write
error or ambiguity without automatic retry, rollback or cleanup.
