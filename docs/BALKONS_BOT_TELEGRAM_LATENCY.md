# Balkons bot Telegram response latency — source-only fix

## Root-cause scope

The previous `balkons-bot.py` called `requests.post(sendMessage, timeout=10)` synchronously
from Paho `on_message`. Because Paho `loop_forever` dispatches callbacks while
processing MQTT network work, slow Telegram HTTP delayed later inbound MQTT
responses. Official references:
- https://eclipse.dev/paho/clients/python/docs/
- https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html
- https://core.telegram.org/bots/api#sendmessage
- https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts

## Contract and boundaries

- MQTT callback and bot-local /start messages only enqueue to a 16-message FIFO.
- A single daemon sender owns blocking HTTP `sendMessage` and retains the
  existing 10-second Requests timeout and exactly one application send attempt.
- Queue full: the newest message is dropped immediately, with a sanitized warning;
  content, credentials, chat IDs and endpoint URLs are never logged.
- For queue waiting or HTTP operations lasting >=1 second, log only
  `queue_ms`, `http_ms`, and numeric `ok`. These are measurements of
  bridge delivery, not end-to-end Telegram/ESP32 command response time.
- No MQTT topic, command QoS/retain policy, publish retry, systemd credential,
  ESP32 firmware, Home Assistant, pump start/stop or relay behavior changes.

## Verification and residual latency

`tests/test-balkons-bot-telegram-queue.py` tests callback isolation during
a slow HTTP send, FIFO order, bounded overflow, one-shot error handling,
command compatibility and sender startup; `make validate` includes it.

There is intentionally no live timing assertion from this source change.
The ESP32 still reads 15 sensors sequentially, may defer outgoing telemetry
while the pump is running, and uses separate MQTT ACK tracking. A queue
build-up or Telegram API outage can still delay/drop responses; production
end-to-end measurements should locate the remaining bottleneck.

## Later manual-watering admission (#1226)

The latency worker remains unchanged: MQTT callbacks only enqueue Telegram HTTP
work. A later source layer now checks a fresh local RPi5 safety-state file before
normal `/laist*` publishes. That file read is local and bounded; it adds no
Telegram/HA network request and no new credential. `/stop` remains direct.

If MQTT rejects a command publish, the bot enqueues one user-facing Telegram
failure message and performs no application retry. This does not claim
end-to-end command delivery or pump state.

## Production safety gate

Merge is separately owner-gated, and source merge does not install or restart
`balkons-bot.service`. Any rollout needs explicit bounded LIVE authority,
sanitized read-only preflight, exact source/artifact identity and recovery
review. Never run MQTT probes/commands, restart host services, read credentials
or flash/actuate ESP32 under this source-only change.

## Existing 11:00 watering Telegram route attribution (#1478, source only)

The November 15, 2026 source/host reconciliation must **not infer** the active
bot's MQTT subscription from `balkons-bot.service=active`, nor infer a failed
bot from an unfamiliar Python filename. The historical live-only, potentially
secret-bearing Python implementation from #192 predates the reviewed
`ops/lib/balkons-bot.py` source. The reviewed initial-install operator from
#925/#932 targets exactly `/usr/local/lib/rpi5-balkons-bot.py` and the
encrypted-credential overlay, but an owner authorization record is **not proof
that installation/restart completed**. Historical #925 owner approvals are not
reusable LIVE authority.

After an independently scoped, **strict READONLY** host authorization, the
source-only `ops/bin/balkons-bot-route-attribution` can classify only
allowlisted `systemctl show` metadata for `balkons-bot.service`: configured
system Python script path **regardless of its basename**, service status and
main PID presence, known legacy *path fingerprint* (not legacy file content),
fixed reviewed public install-target hash and declared encrypted credential
*identifiers*. It reuses the existing reviewed
`ops/bin/balkons-bot-preflight` `ExecStart` parser. It does not read the
private live bot's Python bytes, credentials, proc argv, raw service unit,
environment, logs or MQTT payload; it prints no private path/argv, only a
bounded sanitized classification, path SHA-256 and static status flags.

Possible classifications:

- `REVIEWED_PUBLIC_SOURCE_CONFIGURED`: `ExecStart` references the exact
  public fixed file and its SHA-256 matches reviewed source. Metadata alone
  still **does not verify the running PID's executable, actual MQTT broker
  connection/subscription or delivery to the Telegram chat**.
- `HISTORICAL_LEGACY_PATH_FINGERPRINT_MATCH`: configured path fingerprint
  equals a previously approved #925 private baseline; this proves no legacy
  file bytes or current behavior. Never open that source to inspect topics.
- `OTHER_PRIVATE_SOURCE_UNATTRIBUTED`: some other Python entrypoint; do not
  guess identity from the basename.
- `BLOCKED`: conflicting source metadata, missing/unsafe public fixed
  target when configured, invalid PID/service/ExecStart. No arbitrary fallback.

The five encrypted credential IDs in the public overlay are declarations
only. Metadata cannot establish that credentials decrypt successfully or
that the bot reaches the correct chat; even a running service and successful
MQTT publish are not proof of Telegram receipt.

**Gate for the already merged #1474 11:00 repair:** the current Hermes wrapper
still executes a 12-sensor/obsolete direct-Telegram controller, while its
reviewed replacement sends `Nav laistīts` through HA MQTT
`balkons/telegram_out`. Do **not** replace that controller until the target
bot route and missing protected runtime wiring have independently passed a
separate exactly authorized, sanitized read-only preflight. If the reviewed
bot is not installed, use the existing #925 fixed initial-install operator
*only after a new exact composite LIVE owner decision and its original
no-overwrite/recovery gates*, not an improvised source copy. Bot LIVE
installation, any credential change, and the 11:00 controller file replacement
are distinct trust-boundary operations. No cron change or manual watering
probe is implied or authorized.

Offline regression: `tests/test-balkons-bot-route-attribution.py` runs through
`tests/test-balkons-bot-preflight.py` in the existing balcony CI group; none
of those tests contacts a live host, broker, Telegram or ESP32.

## MQTT SUBACK and Telegram API outcome observability (#1481)

**Scope: source only.** The 2026-11-15 owner-authorized #925 initial
installation placed the reviewed bot and encrypted-credential systemd overlay
on RPi5. A subsequent strictly read-only check showed the service running, but
a bounded journal tail since service start exposed no reliable connection or
delivery markers. Absence of log messages is **not** evidence of a failed MQTT
connection or Telegram delivery: stdout may have been buffered, and normal
fast Telegram sends were previously silent.

The source now emits only fixed, eagerly flushed **stderr** categories:

- `MQTT connected`: broker CONNACK accepted; still **not** a subscription ACK.
- `MQTT subscribe request rejected` / `MQTT subscribe request invalid`:
  the local request could not be established.
- `MQTT SUBACK accepted`: a broker acknowledgment matched the pending
  subscription packet ID, carried exactly one acceptable QoS success reason,
  and was observed for the single reviewed `balkons/telegram_out`
  subscription. A reconnect invalidates the previous pending ID.
- `MQTT SUBACK rejected`, `MQTT SUBACK unknown` or `MQTT SUBACK unmatched`:
  a rejected, malformed, delayed or unrelated acknowledgment. None proves
  the required subscription is active.
- `TG API outcome source=mqtt ok=1`: a message received on the reviewed MQTT
  callback path was accepted by the Telegram Bot HTTP API on **one** send
  attempt. `source=local` identifies independently generated messages
  (including startup). `ok=0` means the request failed. Slow-send
  `queue_ms`/`http_ms` diagnostics remain separate.

This reporting never includes MQTT payloads/topics, bot token, URLs, chat
identifiers, Telegram text, arbitrary exception strings, or per-message
identifiers. It does not add MQTT publishes, Telegram probes, duplicate HTTP
attempts, new retries, service changes or ESP32/pump commands.

**Proof limits:** Broker SUBACK establishes subscription acceptance only on
that particular connection. Telegram `ok=1` is HTTP API acceptance, **not**
human delivery, a chat-read receipt, or independent proof of recipient
correctness. A local startup `ok=1` is **not** evidence that the MQTT
notification route works. For the 11:00 repair, require a current matching
SUBACK and a real MQTT-origin API acceptance event, plus independently
authorized verification of destination wiring and HA publishing capability;
this source change alone cannot provide those observations.

**Production update is separate:** #925's reviewed initial-install operator
rejects existing public source and overlay targets, so it must **never** be
reused to overwrite the live bot. After this source PR is merged by separate
owner decision, prepare a new fixed-source-hash, already-installed update and
rollback/recovery design. Its own exact COMPOSITE STRICT LIVE authorization
must cover every host file replacement and service lifecycle action. No
production operation, broker probe or Telegram send is authorized by this PR.

Offline tests extend the existing `tests/test-balkons-bot-telegram-queue.py`
balcony CI suite with Paho v1/v2 callback signatures, matching/mismatched
SUBACK, malformed/rejected reasons, reconnect invalidation, and source-tagged
HTTP outcome logging without message data.
