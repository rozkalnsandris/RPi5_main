# Existing 11:00 Hermes preflight — one strict script-only alternative (#1515)

**SOURCE ONLY.** This change does not open the live Hermes store, read backups,
change cron, run the controller, publish MQTT, send Telegram, drive the pump
or authorize any installed-file replacement.

## Simplified rule

The **same existing** `ops/bin/balcony-watering-autumn-notify-only-preflight`
is the only preflight required by the existing #1498 one-shot operator.
There is no new four-slot production binding database, historical checksum
reconstruction or separate operational pipeline.

For the 11:00 job, it accepts **either**:

1. The **unchanged pinned historical definition** SHA-256
   `bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562`.
   This is backward compatibility, not a new baseline; **or**
2. The independently specified **strict Hermes script-only contract**:
   exact unique enabled/local `0 11 * * *` autumn job, `no_agent=true`,
   empty prompt, `state=scheduled`, explicit
   `timezone=Europe/Berlin` and `grace_minutes=0`; no queued
   `pending_slot` or `fire_claim`, active LLM model, provider or
   attached skills; bounded allowlisted scheduler bookkeeping;
   no unknown definition fields or extra schedule commands.
   An exact authorized script binding must point to the existing
   `balcony-watering-autumn-run.sh` wrapper.

**Both** branches still require the existing guarded Hermes store read,
unique disabled 07:00/14:00/23:00 legacy slots, no extra watering
candidates, exact on-host wrapper SHA
`3e5698a54d33fafaef59a0bc5c847136672c6658de3a22001058bffe51a4133f`,
old controller SHA
`86972a10bd457abb6350e2f924d7c3bcc54139af322f335707f51e1e440ac60b`,
notification-only candidate SHA
`7c993c5e0fdffdcb405b57aebad2be65a133be17caf13f16492fde6f12bc45b1`,
exact **12-sensor fail-closed behavior**, approved MQTT bot source and
the operator's exact Git checkout/owner/path/mode checks.

The result includes only a fixed public `identity_mode` value:
`pinned_legacy` or `strict_script_only`. The actual current
job SHA may differ in the script-only branch because Hermes updates
runtime counters, repeat progress, timestamps and last-dispatch
metadata. The preflight does **not** copy an observed SHA to a new
production pin and never accepts unknown executable/prompt fields.

Official rationale: [Hermes Cron Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals)
describes mutable job bookkeeping, while
[Script-Only Cron Jobs](https://hermes-agent.nousresearch.com/docs/guides/cron-script-only)
states that `no_agent=true` executes the script without an LLM turn.

## Strict gate remains conditional

The *real* 11:00 runtime job has **not** been read during this source work.
The strict alternative may still return `BLOCKED` if the actual job
lacks these explicit properties; this is intentional and must not be
"fixed" by guessing, repinning from a live SHA, disabling a sensor or
editing the scheduler.

The one-shot #1498 operator recognizes the new strict `identity_mode`
only if **all** wrapper, old/new controller, legacy schedule, sensor and
source-provenance checks still pass. Its one-file replacement and
fail-closed stop/recovery semantics are unchanged. A preflight PASS
means only that **source and bounded runtime evidence matched**; it is
not LIVE authorization or proof of Telegram delivery.

**Next gate:** explicit owner `STRICT READONLY` authorization for the
sanitized existing preflight on `rpi5`, tied to an exact RPi5 source
checkout SHA. Separately verify HA/bot notification delivery and credentials
without printing secrets. Only a later separately owner-approved
`COMPOSITE STRICT LIVE` operation may run the existing one-file
replacement; no merge, preflight, test or source sync authorizes it.

No Hermes job or scheduler edits, no controller execution, no changes to
12-sensor fail-closed logic, no arbitrary source/metadata hashes and no
automatic host changes are part of this PR.
