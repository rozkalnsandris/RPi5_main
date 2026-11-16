# Hermes 11:00 alternative evidence path — forward-only (#1511)

**SOURCE ONLY — decision/runbook. Not a controller release, verified host
observation, new identity pin, scheduler change or LIVE permission.**

## Decision

Prefer a **fresh, independently specified current-job identity and safety
contract** over trying to reconstruct the missing historical definition from
its SHA-256. The new contract must be reviewed against intended source
behavior *before* a protected current-job sample is compared. Neither a
match to the most recently observed hash nor a plausible scheduler-counter
explanation is acceptance evidence.

The historical hash-based comparison from
[the #1509 runbook](BALCONY_AUTUMN_VERIFIED_DEFINITION_COMPARISON_1509.md)
remains useful **only** if a complete provenance-verified historical record
later becomes available. It is not a prerequisite for *designing* the
forward-only route; the original `JOB_SHA256` gate remains binding until a
separate reviewed source change and owner decision.

## Evidence as of 2026-11-16 — not a present runtime assertion

- Reviewed `RPi5_main/main` at discovery:
  `a222ee06143c3035ed487a0c309117896b4899c5`.
- Frozen old 11:00 Gate-1 definition SHA-256:
  `bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562`.
- Last separately authorized sanitized observation:
  `c3609b09eb842f73d8fc78e8828fd350838be9f7453adfcfd6855c56d09c1140`;
  `--diagnose` reported `unclassified`, and operator `--check` reported
  `preflight_job_identity_drift`. No changed field has been proved.
- Later owner-authorized **metadata-only** inventory on `rpi5` found **two**
  private, regular, backup-like direct-child candidates whose file
  modification times classified **before 2026-11-15**. The inventory did
  **not** read contents, identify a historical job, verify provenance, or
  establish either candidate as the old record. No filenames, sizes,
  private values or contents are published here.
- [Hermes Cron Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals)
  describes scheduler-owned runtime changes to job records, including
  `run_count`, `state`, `last_dispatch` and `pending_slot`. The existing
  Gate-1 `_definition_projection` does not exclude all of those fields.
  A one-time hash substitution could therefore fail on a later legitimate
  scheduler update, while wrongly hiding unreviewed definition changes.

## Minimum independently reviewed acceptance specification (not yet available)

Author a **new, source-controlled, versioned expected contract** from
reviewed intended watering behavior, never from an observed live fingerprint.
Until this specification and its safety tests are reviewed, **BLOCKED**.

The prospective pure/offline validator must check all of the following
against an already-selected bounded in-memory current job (without opening
Hermes files itself):

1. Exactly one eligible autumn job; enabled, `deliver=local`, exact
   `0 11 * * *` schedule, approved timezone/grace and accepted active
   scheduler state; reject ambiguous role, duplicate jobs, unknown bindings
   or an unexpected schedule/state. The three 07:00/14:00/23:00 legacy jobs
   must be uniquely identified and disabled; no other watering candidate.
2. Independently approved exact script/prompt/wrapper identity **including
   relevant content digests** and the selected 11:00 executable binding.
   Do not treat display name, substring markers, or a matching live hash as
   proof of the command that will execute. Fail closed for unexpected
   top-level/nested definition keys, unknown value shapes, ambiguous script
   references, additional commands or unverifiable sensitive bindings.
3. The existing protected on-host source gate must *separately* prove the
   installed wrapper SHA
   `3e5698a54d33fafaef59a0bc5c847136672c6658de3a22001058bffe51a4133f`,
   old controller SHA
   `86972a10bd457abb6350e2f924d7c3bcc54139af322f335707f51e1e440ac60b`,
   intended notification-only candidate SHA
   `7c993c5e0fdffdcb405b57aebad2be65a133be17caf13f16492fde6f12bc45b1`,
   clean exact checkout, owner/mode/symlink safety and unchanged
   **12-sensor fail-closed logic**. Do not introduce a pump-driven smoke test.
4. Keep scheduler-derived counters and transport metadata **separate from
   immutable identity**, but do **not** blindly ignore `enabled`, `state`,
   `schedule`, `deliver`, `script`, `prompt`, `timezone` or safety-relevant
   fields. A transition to `paused`, `completed`, an unknown state or an
   unsupported metadata shape is **BLOCKED**, not "harmless drift".
5. Treat notification **source routing** and actual **LIVE delivery** as
   distinct. The reviewed MQTT `balkons/telegram_out` route does not prove
   HA credentials, subscriber delivery or successful Telegram notification.

A proposed change to Gate-1 identity hashing or `JOB_SHA256` requires a
**separate focused issue**, exact expected-contract fixtures, adversarial
offline tests (malicious extra fields, changed sensitive bindings,
schedule/state changes, running/paused transitions, duplicate jobs,
scheduler bookkeeping and non-leak), diff/CI/review and an explicit owner
merge decision. This runbook does **not** implement or approve that change.

## Next bounded evidence gate — only after the validator exists

A *separate* owner `STRICT READONLY` approval must identify:
`HOST=rpi5`, exact checked-out Git SHA, unique current 11:00 Hermes
selection, the validated and reviewed reader/validator entrypoint, maximum
input size, privacy-safe output enum and exact allowed read surface. Only
that allowlisted **current-job** evidence is eligible. Reuse guarded
`_read_store` behavior and never emit raw job records, prompts, scripts,
paths, IDs, tokens, hash preimages, arbitrary keys or unbounded payloads.

The reader/validator must return only fixed public categories for:
identity, schedule, delivery, script/wrapper/controller hashes, sensor
invariants, legacy jobs, source provenance, unsupported fields and
unverified LIVE route. If evidence cannot be obtained under repository
policy, **BLOCKED**. Do not retrieve backup contents, private configuration,
secrets or historical candidate files under this source-only plan.

**STOP** on mismatched/dirty source, ambiguous unique job selection,
unapproved schema/keys, missing independent expected contract, changed
safety/actuator behavior, unsafe file metadata, unavailable privacy
guarantees, conflicting observations or unknown device/runtime state.
A single sanitized historical/current hash comparison, even if equal,
never makes the existing apply operator ready.

## Separate owner decisions after evidence

1. Owner reviews the current-definition report and independently sourced
   expected contract. If acceptable, authorize **a new source-only
   identity-gate implementation/rebinding issue**; do not automatically
   accept `c3609b09…` or overwrite the original pin. If not acceptable,
   remain BLOCKED; no recovery or apply.
2. Only after the new identity gate's final source PR has passed exact-head
   CI/review and been **explicitly merged** may a new narrowly authorized
   `STRICT READONLY` RPi5 preflight revalidate current job, wrapper,
   controller, sensor and route evidence. Merge is never deployment authority.
3. Only after all preflight and independent credential/delivery proofs is
   there a separate exact owner `COMPOSITE STRICT LIVE` decision for the
   existing single-file controller replacement. The original #1498
   operator is **not** ready while `preflight_job_identity_drift` persists.
   A source merge, proof report or normal `START` never allows its `--apply`.

No RPi5/Hermes execution, protected runtime read, backups, cron writes,
service restart, MQTT/HA/Telegram actions, controller install or
ESP32/relay/valve/pump operation is included in this #1511 outcome.
