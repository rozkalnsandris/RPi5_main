# Verified 11:00 Hermes definition comparison (#1509)

**SOURCE ONLY.** This work does not open the live Hermes store, run Hermes
or its cron CLI, read backups or protected config, install a watering
controller, publish MQTT, send Telegram, or touch the ESP32/pump.

## The evidence gap

- Canonical issues #1474 and #1498 contain the historical 11:00 job
  definition fingerprint:
  `bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562`.
- Previous authorized, sanitized RPi5 observation contained current
  fingerprint `c3609b09eb842f73d8fc78e8828fd350838be9f7453adfcfd6855c56d09c1140`.
  Runtime checks from #1505/#1507 found `unclassified`, not a
  causally proved field change.
- The reviewed GitHub issue evidence provides a fingerprint, **not** a
  complete independently verified historical job definition.
  **SHA-256 is not reversible.** No safe field-by-field old-versus-new
  comparison can be claimed until a trusted complete previous definition
  is supplied, provenance checked and its Gate-1 digest matches the
  historical pin.

The official [Hermes Cron Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals)
documents `jobs.json`, its scheduler runtime metadata and job lifecycle.
The existing source's Gate-1 `_definition_projection` is the authoritative
definition hashing contract for this particular original pin. It excludes
selected transient fields, so a comparison of this projection is **not**
a proof that every runtime metadata field was historically unchanged.

## New narrow offline comparator

`ops/lib/balcony_autumn_definition_compare.py` exports a pure,
in-memory `compare_verified_definitions(reference, observed)` function.
It **does not** open files or read the host, does not run an interpreter
on job content, and provides no CLI for accessing protected runtime data.

Its mandatory precondition is a historical **complete** selected job
record whose Gate-1 fingerprint exactly matches
`bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562`.
If unavailable: `BLOCKED / verified_reference_unavailable`.
If different: `BLOCKED / reference_fingerprint_mismatch`.
If the observed job is absent, malformed or oversized: `BLOCKED`.

Only once that old record is *cryptographically bound* does the comparator
compare the two Gate-1 normalized projections and return **fixed safe
definition categories**, without actual values, raw prompts, scripts,
URLs, field names not on the allowlist, IDs or private hashes. Changes to
unrecognized fields are reported only as `other_definition_fields`.
All results, including identical fingerprints or categorized changes,
return `BLOCKED`. They never authorize a hash re-pin, live apply,
new controller, schedule edit or removal of sensor safety checks.

The comparison classifies the *difference of provided records*, not
their historical origin; source-file provenance must be established
separately. An arbitrary job that hashes differently is **not** a
trusted reference. A fixed SHA alone is **not** a complete record.

## Exact next evidence boundary

Before a **real** host comparison, the owner must separately authorize
the exact STRICT READONLY metadata inspection (source SHA, host, selected
11:00 record, privacy contract). Any historical reference must be
independently provenance-verified and matched against the frozen digest,
**without reading backups or raw protected config under source-only
authority**. Do not publish the protected record into GitHub.

If no verified previous definition can be obtained, remain BLOCKED and
request an explicit owner decision for a different evidence path.
Do not synthesize the missing historical record from the observed
fingerprint or an arbitrary Hermes example.

No change to `ops/bin/balcony-watering-hermes-preflight`,
`JOB_SHA256`, the original 11:00 preflight/operator, wrapper,
12-sensor controller candidate, MQTT route, Hermes job or the
controller-install authorization boundary.

The existing balcony test entry executes synthetic comparator tests.
CI validation manifest remains unchanged.
