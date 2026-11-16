# Hermes 11:00 independent in-memory safety classifier (#1513)

**SOURCE ONLY.** No Hermes store/backup/host read, protected-data access,
job execution, MQTT/HA/Telegram, actuator test, cron change or controller
deployment. This is the **implementation precursor** required by
[BALKONS #1511](BALCONY_AUTUMN_HERMES_FORWARD_EVIDENCE_1511.md).

## Present state and provenance

`ops/lib/balcony_autumn_independent_validator.py` exports the pure
`assess_jobs(jobs, *, bindings=PRODUCTION_BINDINGS)` function. Its default
`PRODUCTION_BINDINGS = None` is intentional: **no independently reviewed
complete four-slot script/prompt/name/delivery/timezone/grace binding
contract is presently frozen**. It must **not** be constructed from the
observed current Hermes job, observed `c3609b09…` digest, backup metadata,
or guessed historical `bc085927…` preimage.

The validator accepts bounded **already supplied in-memory** job records.
A synthetic four-slot contract can be supplied explicitly for adversarial
offline tests. This caller-supplied contract **is not authenticated
provenance**; the classifier returns `BLOCKED` and
`source_contract_independently_approved=false` even when all values match.
The module has no CLI, file reads, network, shell, write or actuator path.

The original `JOB_SHA256` remains
`bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562`.
No production Gate-1, existing 11:00 preflight/operator, controller
candidate, old 12-sensor fail-closed behavior, MQTT route or schedule was
changed.

## What this offline check does and does not establish

For an independently specified synthetic contract it requires:

- Exactly one named binding per each known 07:00, 14:00, 23:00 and 11:00
  slot. The three legacy slots must be disabled; autumn must be enabled,
  local, exact `0 11 * * *`, with specified timezone/grace.
- Each job's **entire script and prompt SHA-256** must match the fixture;
  display names and marker substrings are insufficient to authenticate
  executable content. Job IDs must be unique and well-formed. Obvious
  additional watering candidates are blockers, not sufficient proof
  that no undiscovered watering command exists.
- No unreviewed definition keys or extra schedule keys; absent or
  `scheduled` state only. `running`, `paused`, `completed` and unknown
  scheduler state are blocked. The potentially dispatchable
  `pending_slot` is **always blocked**, even if well formed. Bounded
  `run_count`, timestamps and strictly shaped `last_dispatch` can
  appear as metadata without changing script identity; unrecognized
  metadata shapes block.
- A strict maximum of 64 job records and 100,000 serialized characters
  avoids unbounded processing. No raw values, names, paths, SHA-256
  strings or unknown keys appear in the report.

An in-memory fixture match **does not prove** that the inspected selection
is all of the live Hermes store, that a caller supplied independently
approved bindings, that the legacy jobs/actor are safe at runtime, that
the installed wrapper/controller digests are valid, that all 12
moisture-sensor gates are functioning, or that Telegram notifications
reach the destination. Only the separately owner-authorized
read-only preflight plus additional actual-device evidence could check
those. **There is no "PASS"/ready/deploy result.**

## Exact next gate (not authorized by #1513)

1. Independently review the *intended* four-slot source bindings and
   settle all expected SHA-256s, name, delivery, timezone and grace
   from vetted source/owner evidence; represent them in a **separate
   reviewed source-only change**, with fixtures and adversarial tests.
   Do **not** derive them from the current runtime sample or
   auto-rebind `JOB_SHA256`.
2. Only with a reviewed source contract and a separately owner-approved
   `STRICT READONLY` access envelope may a future **bounded,
   independently reviewed, sanitized** host reader select the unique
   current 11:00 job and compare in memory. This module must not be
   changed to read `jobs.json` itself, inspect backups, print data or
   mutate the scheduler.
3. Preserve the old gate fail-closed. Any decision to replace or
   rebind it requires another explicit owner source decision, reviewed
   code/test/CI, exact-head MERGE and a **separate** owner LIVE decision.
   The existing #1498 operator must remain BLOCKED while its frozen
   job digest does not match. No `--apply` or pump-driven test.

## Offline regression

The existing `tests/test-balcony-watering-autumn-notify-only-preflight.py`
suite exercises this classifier with synthetic data, including benign
bookkeeping, harmful pending dispatch/state/definition drift, duplicates,
unknown fields, malformed/oversized input, privacy and unconditional
BLOCKED semantics. The existing balcony CI group already invokes this
suite; no CI manifest change is required.

**STOP** for incomplete independently reviewed bindings, unknown
schema, ambiguous selection, altered schedule/enable/delivery, script
or prompt drift, unsafe state/pending slot, unverified source/host,
sensor uncertainty, unclear credentials or actual delivery.
