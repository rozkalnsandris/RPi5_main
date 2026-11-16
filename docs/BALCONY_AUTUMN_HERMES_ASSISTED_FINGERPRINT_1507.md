# Hermes-assisted 11:00 fingerprint diagnosis (#1507)

**SOURCE ONLY — no RPi5 or Hermes runtime action.** This follows the
successfully merged #1505 and the separately owner-authorized, strictly
read-only RPi5 diagnostic which returned `unclassified`.

## What was verified

- Reviewed pinned 11:00 Hermes job definition fingerprint:
  `bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562`.
- Sanitized observed definition fingerprint:
  `c3609b09eb842f73d8fc78e8828fd350838be9f7453adfcfd6855c56d09c1140`.
- The single-field `run_count` reconstruction did **not** explain that
  observation. **No actual changed field has yet been identified.**
- Wrapper/controller hashes still matched; successful Telegram smoke
  proves the notification bot's path, not the Hermes wrapper's HA token.
  Host/schedule/device state remains subject to fresh independent evidence.

## Why Hermes metadata might change the fingerprint

Hermes [official Cron Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals)
describes periodic scheduler changes to `run_count`, `state`,
`next_run_at`, `last_dispatch`, `pending_slot`, and
`repeat.completed` while `jobs.json` is rewritten. The existing
`ops/bin/balcony-watering-hermes-preflight` projection already excludes
several runtime fields and `repeat.completed`, but currently *includes*
`run_count`, `state`, `last_dispatch`, and `pending_slot`.

The optional read-only `--diagnose` now runs bounded, SHA-**exact** tests
against **hypothetical prior definitions**, with only fixed public-safe
categories (never the values, names, IDs, paths, or arbitrary field keys):

- existing `run_count_added_only` / `run_count_increment_only`;
- `last_dispatch_added_only` / `pending_slot_added_only`;
- `run_count_plus_last_dispatch_added_only` /
  `run_count_plus_pending_slot_added_only`;
- `last_dispatch_and_pending_slot_added_only`;
- `state_added_only` / `state_transient_only` for the explicit
  `scheduled` ↔ `running` pair only;
- `unclassified` when no candidate reconstructs the reviewed hash,
  types/bounds are invalid, or multiple candidates appear.

Only metadata dictionaries of at most 16 keys and 4096 encoded characters
are eligible; prior run-count search is bounded by the existing 512 steps.
No secret or source of truth is sent to Hermes, no Hermes CLI is run, and
**the production job definition is not modified**.

## Nonnegotiable safety property

All diagnostic categories are just *hash-reconstruction hypotheses*,
not proof of why the runtime record changed. No previous full record is
available for direct diff. The check **ALWAYS returns BLOCKED** for a
fingerprint mismatch, even if a reversible candidate matches.

The frozen expected job hash, 11:00 delivery/schedule checks, 12-sensor
fail-closed policy, controller/wrapper hashes, MQTT topic, actuator checks,
and `--apply` authorization remain unchanged. Never silently re-pin
a live hash or ignore `state` because it is scheduler-controlled;
`paused` and `completed` are especially safety-significant.

After explicit **owner STRICT READONLY** scope (not supplied by this
source-only work), run the reviewed merged `--diagnose` against the one
11:00 job, printing only sanitized JSON. A PR or merge does not authorize
host checkout changes, protected config reads, activation or installation.
If result stays `unclassified`, STOP: obtain an independently approved
sanitized comparison or evidence about exact definition history.

The 11:00 notify-only file replacement remains **BLOCKED** pending
separate safe host gates, Hermes HA wrapper credential proof, matching
immutable reviewed identity and explicit COMPOSITE STRICT LIVE approval.

Offline synthetic tests reuse the existing balcony validation command;
no CI manifest changes. No RPi5 host, MQTT, Telegram, or pump mutation.
