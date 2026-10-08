# Balcony bot latency rollout: guarded source-only plan (#920)

## Current provenance and reusable source

The Telegram HTTP callback fix was merged in RPi5_main PR #919. Neither its merge
nor green CI proves that the production service is running the new source.
Reuse the existing checked-in assets: `ops/lib/balkons-bot.py`,
`ops/bin/balkons-bot-preflight`, `ops/bin/balkons-bot-deploy-verifier`,
and `ops/systemd/balkons-bot-runtime-override.conf`. The last file uses exactly
five encrypted systemd credentials. Never inspect credential bytes.

## Offline source bundle and candidate classifier

The executable `ops/bin/balkons-bot-latency-rollout-plan` is OFFLINE-ONLY:
it hashes six fixed, public, tracked source files and validates the fixed
JSON contract in `ops/contracts/balkons-bot-latency-rollout-v1.json`.
Invoke with `python3 ops/bin/balkons-bot-latency-rollout-plan --expected-repo-sha <EXACT_SHA>`.
Without runtime evidence it returns `BLOCKED / evidence_not_supplied`.
An optional `--sanitized-evidence-stdin` consumes at most 16 KiB of JSON
with exact keys: schema, target_alias, checkout, verifier, preflight,
credential_metadata, credential_content_read, historic_source, service,
lifecycle, forward_targets, root_backup, rollback_plan, repo_sha,
source_sha256, bundle_sha256. Unknown fields or drift fail closed.
The evidence must be a narrow projection from independently authorized,
verified read-only receipts, not a hand-entered assertion.
Even when all projected gates pass, output is only `SOURCE_CANDIDATE`.
Neither this result nor the CLI grants MERGE/LIVE or performs any host action.

## Bound initial-install operation — not executed by this source work

1. Review exact merged repo SHA and hashes of the bot source, overlay,
   preflight and deployment verifier; prove clean tracked `main` on `rpi5`.
   An exact host checkout fetch/fast-forward is separately gated.
2. With separately authorized metadata-only preflight, check the historic
   source provenance and the service `ActiveState=active`, `SubState=running`,
   `Restart=always`, `RestartUSec=10s`, `TimeoutStopUSec=1min 30s` and
   `SendSIGKILL=no`. Never inspect private unit or process environments;
   only separately authorized preflight may hash the historic live source
   without printing, copying, or returning its contents.
3. Check all five encrypted credential objects for root owner, type, one link,
   mode 0400 and size bounds only. Any unknown/missing state means BLOCKED.
4. Require the existing `balkons-bot-deploy-verifier --check` to pass. It
   explicitly requires BOTH initial-install targets ABSENT. Existing targets
   mean BLOCKED; this issue does not authorize replacing an installed bot.
5. Under distinct later owner LIVE authority, a reviewed root-only executor
   must first build and verify a private rollback bundle bound to the exact
   pre-deploy source/service/lifecycle. This itself is a host mutation.
6. Only when separately authorized, install EXACT public bytes into the two
   fixed destinations: `/usr/local/lib/rpi5-balkons-bot.py` and
   `/etc/systemd/system/balkons-bot.service.d/95-rpi5-source-credentials.conf`.
   Require root:root, regular one-link 0644, never touch K10 or ciphertext.
   Then exactly one reviewed `systemctl daemon-reload` and one
   `systemctl restart balkons-bot.service` if frozen in LIVE scope.
7. Require `balkons-bot-deploy-verifier --verify`, service running and bounded
   privacy-safe response timing. Preserve `SendSIGKILL=no`; no kill fallback.
   After first LIVE mutation, any uncertainty means STOP; no automatic
   retry, rollback, cleanup or alternate executor without preauthorization.

**Remaining prerequisite:** No root-capable install/backup/rollback executor
is introduced in this PR. `SOURCE_CANDIDATE` does not establish that a
production operation is executable. A fixed reviewed executor and exact
backup/restore semantics need to be proven before seeking LIVE approval.

## End-to-end /mitrums diagnostic acceptance

Compare `/mitrums` and `/statuss`, pump OFF and ON. On the RPi5 bot,
sanitized `TG delivery timing queue_ms`, `http_ms`, `ok` distinguish
slow Telegram delivery from MQTT callback scheduling. ESP32 serial sensor
reads, pump-on MQTT publish suppression and QoS1 ACK remain independent
sources of lag. No live MQTT command/probe or pump operation is permitted
by this issue. Do not persist raw MQTT payloads, chat IDs, credentials,
token-bearing URLs, systemd configuration, or protected host data.

## Owner gates

Issue #920 retains a separate exact-head MERGE gate. Source merge still
does not install anything. Host checkout, secret provisioning, root-owned
file installation, service lifecycle and real acceptance evidence each
require their appropriate separate exact authorization.
