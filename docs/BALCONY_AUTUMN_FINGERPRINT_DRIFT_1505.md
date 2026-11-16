# 11:00 Hermes fingerprint drift — offline source correction (#1505)

**SOURCE ONLY.** No RPi5 runtime read, protected config/secret access, host
mutation, controller install, MQTT publish, Telegram send, or pump command
was performed for this work. The existing 12-sensor autumn controller and
every schedule/actuator/credential gate remain unchanged.

## Evidence, not assumptions

- Frozen reviewed 11:00 job definition SHA-256:
  bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562.
- Last **sanitized, explicitly authorized** on-host observation returned
  c3609b09eb842f73d8fc78e8828fd350838be9f7453adfcfd6855c56d09c1140
  and the precise preflight reason `autumn_job_identity_drift`.
- The unique enabled/local 11:00 job and three disabled older jobs were
  recognized. Existing wrapper SHA-256
  3e5698a54d33fafaef59a0bc5c847136672c6658de3a22001058bffe51a4133f
  and deployed controller SHA-256
  86972a10bd457abb6350e2f924d7c3bcc54139af322f335707f51e1e440ac60b
  still matched.
- GitHub `main` at source-lane discovery was
  fb07294098f4a46896c9d39232f054061da94b36. The verified bot
  delivered the fixed single HA MQTT smoke message to the correct
  “Balkona Laistīšana” conversation. This independently confirms the
  **bot notification path**, NOT the 11:00 Hermes wrapper HA auth.
- The operator previously returned `internal_error` because an imported
  preflight raised its **own** `Blocked` class. The revised operator now
  maps the recognized `autumn_job_identity_drift` to the fixed public
  `preflight_job_identity_drift`; all other preflight blockers map to
  `preflight_not_ready`. No bypass or retry was introduced.

## Hermes documentation and specific hypothesis

Official Hermes [Cron Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals)
describes a persistent `jobs.json` whose execution modifies `run_count`,
`next_run_at`, `repeat.completed` and the lifecycle `state`.
The existing project `_definition_projection` excludes many runtime
fields and `repeat.completed`, but not `run_count`.

Thus a daily `run_count` increment **could** change the pinned fingerprint
despite identical scheduling, script and notification routes. This is
**not yet proved** from the observed digest alone. Do NOT update the
frozen SHA to the current digest or silently exclude mutable fields.

## Optional future sanitized READONLY diagnosis

After a **separate, strict owner READONLY authorization** scoped to the
existing Hermes 11:00 store and this exact script, run the reviewed
preflight with `--diagnose`. The original preflight checks remain
mandatory and **BLOCKED on any fingerprint mismatch**.

On that one mismatch, the diagnostic tests only whether replacing **one**
documented runtime `run_count` by a bounded earlier integer, or deleting
a newly added `run_count` field, reconstructs the frozen SHA-256.
Only three fixed public result categories are possible:

- `run_count_increment_only` — SHA proves the prior definition could
  differ solely in this counter (bounded historical reconstruction).
- `run_count_added_only` — SHA proves this field alone was added.
- `unclassified` — no such proof; cannot assume a harmless change.

Results never contain the counter itself, jobs, IDs, prompts, scripts,
chat IDs, protected paths or configuration. No raw/private store may be
printed or uploaded to GitHub. `--diagnose` always returns a **nonzero
BLOCKED** for the observed mismatch. Even a counter-only category is
**not** a release PASS, authorization to re-pin a hash or proof of active
pump/sensor/frost state.

An independent owner decision after real evidence would be required
to design, review, test and merge an invariant-preserving fingerprint
schema migration. That is a distinct follow-up, not part of #1505.

## Release boundary

A future controller replacement remains blocked pending canonical
exact-head source approval, separate sanitized authorized host checks,
unchanged 11:00 job + wrapper/controller identity, verified Hermes HA
credentials, no active watering and an exact COMPOSITE STRICT LIVE owner
command. Preserve the legacy 12-sensor fail-closed logic; never silently
substitute the separate 10-sensor source.

No changes were made to `RUNTIME_FIELDS`, `JOB_SHA`, either controller,
the bot, 11:00 schedule, wrapper, protected credentials or any actuator.

Offline CI reuses existing
`tests/test-balcony-watering-autumn-notify-only-preflight.py` and
`tests/test-balcony-watering-autumn-notify-only-operator.py` entries.
The validation manifest count remains 318.
