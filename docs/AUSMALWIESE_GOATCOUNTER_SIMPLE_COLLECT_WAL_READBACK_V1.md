# GoatCounter SIMPLE: active-WAL Collect readback (source-only, #1360)

**SOURCE ONLY. NOT AN AUTHORIZED LIVE RUNNER.** This bounded Python helper
prepares one sanitized read of the existing GoatCounter v2.7.0 site's
SiteSettings.Collect setting from a SQLite database used by an active writer.
It has **no CLI, privileged entrypoint, installer or service change**.
It is not invoked on the RPi5 by CI/tests and cannot assert current LIVE state.

## Why normal mode=ro, not immutable=1

SQLite's official URI documentation states that mode=ro opens a database
read-only. immutable=1 additionally disables locking/change detection and
is unsafe for an actively changing database: stale or corrupt query results
may occur. SQLite 3.22+ supports reading an existing WAL-mode database if
the -wal and -shm files already exist and are readable; a constrained
runtime should have no permission to create them. This helper therefore
requires both safe, pre-existing sidecars, rejects an overlapping rollback
journal, opens ?mode=ro&cache=private with zero busy timeout, and uses a
bounded BEGIN/single-SELECT/PRAGMA query_only=ON transaction. It does
not delete, checkpoint or rename WAL files, and never asks SQLite to create
the database. Ambiguity or busy/invalid DB state yields STOP_*.

**Important:** mode=ro and query_only do not guarantee zero host writes to
SQLite's *existing shared-memory index*. A future protected read must use a
separately reviewed, owner-approved, OS-restricted runtime and explicitly
verify the live permission/mount semantics. The source helper alone is not
a proof that every byte and filesystem timestamp stays unchanged.

## Fixed output contract

read_once(path) returns exactly one fixed string. Successful statuses are
COLLECT_DISABLED_1 (historical/observed disabled setting) or
COLLECT_CANDIDATE_130 (sessions+referrer candidate, **not approved**).
All other masks, malformed settings/duplicate JSON collect keys, unknown
sites, conflicting rows, unsafe paths/sidecars or DB failures return fixed
STOP_* codes. No raw SQL results, error messages, database paths, visitor
addresses, settings JSON, token material or account identities are emitted.
The helper uses a fixed VHOST parameter and queries no other tables.

No Collect value has been read from the real RPi5 by this source change.
Even COLLECT_CANDIDATE_130 is not an owner privacy approval or evidence
that the running GoatCounter has reloaded the persisted setting.

## Independent owner gates, before any host action

1. Exact trusted release, identity/permissions and minimal source sync if
   needed; no user-supplied arbitrary code, path, or SQLite connection.
2. Explicit **protected, sanitized** GoatCounter DB/settings read approval,
   with non-writable constrained reader and final host safety preflight.
3. Separate Cloudflare Tunnel/Worker GET permission + trusted runtime;
   independent client-IP trust/spoof-negative evidence; reviewed German
   Datenschutzerklärung; exact owner approval for settings/public tracking.
4. New explicit authority for **any** RPi5/Cloudflare mutation; a GitHub
   source merge alone authorizes no LIVE or analytics activation.

Existing scripts/ausmalwiese_goatcounter_retention_v1.py stays unchanged:
its stopped-service/immutable offline protocol is deliberately different.
Do not use it to inspect a live WAL database.

## Offline tests

python3 tests/test-ausmalwiese-goatcounter-simple-collect-readback-v1.py

Official SQLite references:
- https://www.sqlite.org/uri.html
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/c3ref/open.html
