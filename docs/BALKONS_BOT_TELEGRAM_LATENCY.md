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

## Production safety gate

Merge is separately owner-gated, and source merge does not install or restart
`balkons-bot.service`. Any rollout needs explicit bounded LIVE authority,
sanitized read-only preflight, exact source/artifact identity and recovery
review. Never run MQTT probes/commands, restart host services, read credentials
or flash/actuate ESP32 under this source-only change.
