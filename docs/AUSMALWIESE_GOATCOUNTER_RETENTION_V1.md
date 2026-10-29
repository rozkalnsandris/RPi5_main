# Private GoatCounter native retention

Source-only delivery for #1272. Neither this document, its flags, nor a source
merge authorizes host access, service changes, database writes, or public tracking.

## Decision and upstream behavior

The owner selected **12 months** for aggregate pageviews and retained automatic
measurement as the direction for legal assessment. This plan proposes a **365-day
threshold** using GoatCounter's existing daily cleanup. It is not an exact
calendar-month implementation: leap years, day/hour aggregation, the daily run
schedule, downtime and failures affect the actual boundary. The future notice
must describe that behavior honestly; do not promise instantaneous physical
erasure. No live retention setting has yet been observed or changed by this work.

The installed upstream version is v2.7.0, commit
`7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4`:

- [settings.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/settings.go):
  JSON `data_retention`, positive range 31..1825 days; `collect=1` means CollectNothing.
- [cron/cron.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/cron/cron.go)
  and [cron/tasks.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/cron/tasks.go):
  daily retention task, nonpositive values skipped; individual failures are logged.
- [site.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/site.go)
  and [helper.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/helper.go):
  transactional deletion of old aggregates/hits and unreferenced paths, using a
  SQLite UTC day interval; no guarantee about backups or SQLite free pages.
- [cmd/goatcounter/db.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/cmd/goatcounter/db.go):
  no retention option on `db update site`. Do not invent one.

No additional retention timer, service, API token, package or upgrade is needed.
The narrow helper updates the native JSON key inside SQLite without selecting or
printing the complete settings object (which can contain a sharing secret).

## Operator boundary

`scripts/ausmalwiese_goatcounter_retention_v1.py` has no network calls, credential
loader, service mutations or configurable production path. Its CLI requires host
`rpi5`, effective user `ausmalwiese-goatcounter` (not root), secure ancestors,
private database ownership/mode, and both exact services loaded/inactive/dead with
PID zero. Symlinks, hardlinks and any residual WAL/SHM/journal cause STOP.

Only `/var/lib/ausmalwiese-goatcounter/goatcounter.sqlite3` is opened. Read scope:
SQLite schema types/names, expected single-site identity/state, JSON shape and key
uniqueness, `collect`, `ignore_ips`, `data_retention`, and empty/nonempty tests on
the fixed analytics/export tables listed in the script. No visitor rows, users,
passwords, tokens, backup contents or other settings are selected for output.
SQLite necessarily accesses its database pages; this is protected database access,
not an exemption from authorization merely because output is sanitized.

Default mode is read-only and requires `--confirm-read READ_GOATCOUNTER_RETENTION`.
Apply additionally requires `--apply --confirm-apply SET_PRIVATE_GOATCOUNTER_RETENTION_365`.
Both require an empty analytics database and the expected active, parentless site
`goatcounter.ausmalwiese.invalid`, `received_data=0`, `collect=1`, `ignore_ips=""`.
Only missing/zero or already-365 retention is accepted. Other values, extra sites,
schema drift, triggers/views, duplicate JSON keys or existing data cause STOP.

Apply uses one immediate transaction and at most one UPDATE to `sites.settings`.
All other JSON values survive unchanged. Already-365 is a no-op. Missing databases
are never created. A failure before COMMIT discards the uncommitted transaction;
there is no post-commit rollback, retry, deletion, vacuum or recovery operation.
Output is fixed booleans/numeric retention and a fixed STOP stage, never raw errors.

## One bounded future Composite Live

Freeze the final merged source SHA and helper hash before requesting authority.
The scope is protected database inspection plus one native settings update and
stop/start of exactly the following two services on `rpi5`, through Codex SSH with
scoped sudo/runuser. An exclusive operator window is required: no other root,
service manager or database writer may restart/write while the helper runs.

1. Verify pinned source bytes locally and on the host, the installed v2.7.0 binary
   and the two unit/adapter/contract hashes against the private-install receipt.
   Hash those exact files only; do not print raw unit/configuration contents.
   Read allowlisted service metadata (LoadState, ActiveState, SubState, MainPID,
   NRestarts, UnitFileState). Require both services active/running/enabled and the
   expected loopback-only listeners 9193/9194. Stop on mismatch before mutation.
2. Stop `ausmalwiese-goatcounter-pageview.service` once, then stop
   `ausmalwiese-goatcounter.service` once. Wait for each bounded systemctl command
   to finish and require inactive/dead/PID zero. Do not stop any other service.
3. Deliver the exact helper via verified stdin to `python3 -I -B`, using scoped
   `runuser -u ausmalwiese-goatcounter`; no checkout update or installed helper is
   necessary. Run its default read-only mode once. Require PASS and empty data.
   Missing/zero retention is eligible; 365 is eligible as a no-op. Never override
   any STOP or broaden the database read to diagnose it in the same operation.
4. Run apply once, then a fresh read-only check once. Require PASS, 365 days and
   empty data. No manual aging/deletion, test events or synthetic rows in this DB.
5. Start the backend once, then the adapter once. Require the same enabled state,
   both active/running and no restart loop; require loopback-only 9193/9194. Make
   exactly two body-discarding local GETs: backend `/` with its private Host header
   (200/302/303), adapter `/api/pageview` with Host `ausmalwiese.de` (405). Do not
   follow redirects, send POSTs or contact public endpoints.
6. Record a sanitized receipt: exact source/hash, empty-data checks, retention=365,
   service/listener/GET results, writes=0 or 1, pageview_events_sent=0 and public
   collection not enabled by this operation. Return to GitHub for continuity.

Maximum four service lifecycle commands (stop/start each once), one SQLite UPDATE,
two GETs, no credential reads. The native daily cleanup becomes configured for
future data; this operation verifies configuration and startup, not a successful
future daily deletion cycle. SQLite's transient journal is part of the transaction.
No database backup/export, permission repair, credential rotation, tunnel, Worker,
DNS, application rollout or public activation is included.

**Failure semantics:** after either stop or any later mutation, preserve sanitized
evidence and STOP immediately. Services may remain stopped, or retention may be
committed while startup fails. Do not restart as recovery, retry, delete sidecars,
roll back or clean up without a new bounded owner decision. Automatic SQLite
discard of an uncommitted transaction is part of the operation, not a recovery run.

GitHub cannot inspect this private runtime or apply this database setting, and
GitHub-hosted CI uses synthetic files only; this is the precise Codex-SSH exception.
Previous install/read-only authorizations are completed and not reusable.

## Public-release boundary

This change can complete the private configuration independently of public release.
The automatic JavaScript measurement basis remains assessed in
[coloring-pages #158](https://github.com/rozkalnsandris/coloring-pages/pull/158).
365-day configuration does not settle TDDDG scope/exemption, GDPR necessity and
balancing (including the existing Stats view), or edge logs/backups. No blanket
cookie-free exemption, absence of IP processing everywhere, or legal signoff is
claimed. Public client #391 and ingress activation remain separately held.

## Validation

Run `python3 tests/test-ausmalwiese-goatcounter-retention-v1.py` (also in `make test`).
Tests use disposable SQLite fixtures and mocked metadata, not a production copy.
They cover exact-field preservation, no-op, malformed/custom settings, identity,
all analytics-table emptiness guards, missing DB/schema, hidden trigger writes,
precommit failure atomicity, credential-table nonaccess, service states, filesystem
guards, confirmation requirements and output redaction.
