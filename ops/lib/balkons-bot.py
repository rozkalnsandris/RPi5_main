#!/usr/bin/env python3
"""Telegram <-> MQTT bridge for the balcony irrigation controller.

Runtime-only values are read from systemd's $CREDENTIALS_DIRECTORY.
No credential value is accepted through argv, committed source, or a
secret-specific environment variable.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import requests

MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
MQTT_LOOP_TIMEOUT_S = 0.05
TELEGRAM_SEND_QUEUE_SIZE = 16
TELEGRAM_SLOW_SEND_S = 1.0
T_CMD = "balkons/cmd"
T_OUT = "balkons/telegram_out"

SAFETY_STATE_SCHEMA = "rozkalns.balcony-watering-safety.v1"
SAFETY_STATE_DEFAULT_MAX_AGE_S = 6 * 60 * 60
SAFETY_STATE_MAX_BYTES = 4096
SAFETY_STATE_KEYS = {
    "schema",
    "generated_at_epoch",
    "decision",
    "frost_blocked",
    "sensor_total",
    "sensor_degraded_count",
    "sensor_coverage_ok",
    "already_watered_today",
}

_telegram_token = ""
_allowed_chat_id = ""
_mqtt_host = ""
_mqtt_username = ""
_mqtt_secret = ""
_mqttc: mqtt.Client | None = None
_outbound_messages: queue.Queue[tuple[str, float]] = queue.Queue(
    maxsize=TELEGRAM_SEND_QUEUE_SIZE
)


def read_credential(directory: Path, name: str) -> str:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"missing credential: {name}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"empty credential: {name}")
    return value


def _safe_error(prefix: str, exc: BaseException) -> None:
    # Never stringify request exceptions: Telegram embeds the bot token in
    # the request URL, and HTTP/network exception text may include that URL.
    print(f"{prefix}: {type(exc).__name__}", file=sys.stderr)


def _telegram_url(method: str) -> str:
    return f"https://api.telegram.org/bot{_telegram_token}/{method}"


def _telegram_response(response: requests.Response) -> dict[str, Any]:
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise RuntimeError("Telegram API returned an unsuccessful response")
    return data


def _send_telegram_now(text: str) -> bool:
    """HTTP is owned by the sender thread, never an MQTT callback."""
    try:
        response = requests.post(
            _telegram_url("sendMessage"),
            data={"chat_id": _allowed_chat_id, "text": text},
            timeout=10,
        )
        _telegram_response(response)
        return True
    except Exception as exc:  # no raw URL/token, no automatic duplicate send
        _safe_error("TG send error", exc)
        return False


def tg_send(text: str) -> None:
    """Stage one bounded best-effort message without blocking on HTTP."""
    try:
        _outbound_messages.put_nowait((text, time.monotonic()))
    except queue.Full:
        # Never journal Telegram text or MQTT payload contents.
        print("TG outbound queue full; newest message dropped", file=sys.stderr)


def _telegram_sender_loop() -> None:
    while True:
        text, queued_at = _outbound_messages.get()
        try:
            send_started = time.monotonic()
            delivered = _send_telegram_now(text)
            send_ended = time.monotonic()
            queue_delay = max(0.0, send_started - queued_at)
            http_delay = max(0.0, send_ended - send_started)
            if queue_delay >= TELEGRAM_SLOW_SEND_S or http_delay >= TELEGRAM_SLOW_SEND_S:
                print(
                    f"TG delivery timing queue_ms={int(queue_delay * 1000)} "
                    f"http_ms={int(http_delay * 1000)} ok={int(delivered)}"
                )
        finally:
            _outbound_messages.task_done()


def _start_telegram_sender() -> None:
    threading.Thread(
        target=_telegram_sender_loop,
        name="balkons-telegram",
        daemon=True,
    ).start()

def _connected(client, reason_code) -> None:
    if reason_code != 0:
        print("MQTT connection rejected", file=sys.stderr)
        return

    print("MQTT connected")
    result, _mid = client.subscribe(T_OUT)
    if result != mqtt.MQTT_ERR_SUCCESS:
        print(f"MQTT subscribe failed rc={result}", file=sys.stderr)


def on_connect_v2(client, userdata, connect_flags, reason_code, properties) -> None:
    del userdata, connect_flags, properties
    _connected(client, reason_code)


def on_connect_v1(client, userdata, flags, rc) -> None:
    # Compatibility only for Paho 1.x runtimes that do not provide the
    # versioned callback API. Paho 2.x always uses VERSION2 above.
    del userdata, flags
    _connected(client, rc)


def on_message(client, userdata, msg) -> None:
    del client, userdata
    text = msg.payload.decode("utf-8", errors="replace")
    # The payload is intentionally delivered to the authorized Telegram chat,
    # but is not duplicated into the service journal.
    tg_send(text)


def _strict_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _safety_state_max_age_s() -> int | None:
    raw = os.environ.get("BALCONY_SAFETY_STATE_MAX_AGE_SECONDS", "").strip()
    if not raw:
        return SAFETY_STATE_DEFAULT_MAX_AGE_S
    try:
        value = int(raw, 10)
    except ValueError:
        return None
    if value < 60 or value > 86400:
        return None
    return value


def _manual_watering_admission(now_epoch: int | None = None) -> tuple[bool, str]:
    raw_path = os.environ.get("BALCONY_SAFETY_STATE_FILE", "").strip()
    max_age_s = _safety_state_max_age_s()
    if not raw_path or max_age_s is None:
        return False, "RPi5 drošības stāvoklis nav konfigurēts"

    path = Path(raw_path)
    try:
        if path.is_symlink() or not path.is_file():
            return False, "RPi5 drošības stāvoklis nav pieejams"
        size = path.stat().st_size
        if size <= 0 or size > SAFETY_STATE_MAX_BYTES:
            return False, "RPi5 drošības stāvoklis nav derīgs"
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False, "RPi5 drošības stāvoklis nav derīgs"

    if not isinstance(data, dict) or set(data) != SAFETY_STATE_KEYS:
        return False, "RPi5 drošības stāvoklis nav derīgs"
    if data.get("schema") != SAFETY_STATE_SCHEMA:
        return False, "RPi5 drošības stāvokļa versija nav derīga"

    generated = data.get("generated_at_epoch")
    sensor_total = data.get("sensor_total")
    degraded = data.get("sensor_degraded_count")
    if (
        isinstance(generated, bool)
        or not isinstance(generated, int)
        or isinstance(sensor_total, bool)
        or not isinstance(sensor_total, int)
        or isinstance(degraded, bool)
        or not isinstance(degraded, int)
        or sensor_total != 10
        or degraded < 0
        or degraded > sensor_total
        or not isinstance(data.get("frost_blocked"), bool)
        or not isinstance(data.get("sensor_coverage_ok"), bool)
        or not isinstance(data.get("already_watered_today"), bool)
        or not isinstance(data.get("decision"), str)
    ):
        return False, "RPi5 drošības stāvoklis nav derīgs"

    now = int(time.time()) if now_epoch is None else now_epoch
    age = now - generated
    if generated > now + 60 or age < 0 or age > max_age_s:
        return False, "RPi5 drošības pārbaude ir novecojusi"

    if data["already_watered_today"]:
        return False, "šodien jau laistīts"
    if data["frost_blocked"] or data["decision"] == "block_frost":
        return False, "sala risks"
    if not data["sensor_coverage_ok"] or data["decision"] == "block_sensor_coverage":
        return False, "nepietiek derīgu mitruma sensoru"
    if data["decision"] != "manual_permit":
        return False, "RPi5 drošības pārbaude pašlaik neļauj laistīt"
    return True, ""


def _publish_command(payload: str) -> bool:
    if _mqttc is None:
        print("MQTT client unavailable", file=sys.stderr)
        return False
    try:
        info = _mqttc.publish(T_CMD, payload)
    except Exception as exc:
        _safe_error("MQTT publish error", exc)
        return False
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"MQTT publish failed rc={info.rc}", file=sys.stderr)
        return False
    return True


def _publish_command_with_feedback(payload: str) -> bool:
    delivered = _publish_command(payload)
    if not delivered:
        tg_send("⚠️ Komanda netika nosūtīta uz laistīšanas kontrolieri.")
    return delivered


def _handle_manual_watering(payload: str) -> None:
    allowed, reason = _manual_watering_admission()
    if not allowed:
        tg_send(f"⛔ Laistīšana bloķēta: {reason}.")
        return
    _publish_command_with_feedback(payload)


def handle_command(text: str) -> None:
    text = text.strip()

    if text == "/laist":
        _handle_manual_watering("laist")
    elif text.startswith("/laist_"):
        _handle_manual_watering(f"laist_{text[7:]}")
    elif text == "/stop":
        _publish_command_with_feedback("stop")
    elif text == "/mitrums":
        _publish_command_with_feedback("mitrums")
    elif text == "/statuss":
        _publish_command_with_feedback("statuss")
    elif text == "/raw":
        _publish_command_with_feedback("raw")
    elif text == "/start":
        tg_send(
            "🌱 Balkona Laistīšana\n\n"
            "/laist — 30 sek (vajag svaigu RPi5 drošības pārbaudi)\n"
            "/laist_2 — 2 min (vajag svaigu RPi5 drošības pārbaudi)\n"
            "/stop — apturēt (vienmēr tiešs)\n"
            "/mitrums — sensori\n"
            "/statuss — info\n"
            "/raw — ADC vērtības"
        )
    else:
        tg_send("Nezināma komanda. Sūti /start")


def telegram_loop() -> None:
    offset = 0
    while True:
        try:
            response = requests.get(
                _telegram_url("getUpdates"),
                params={"offset": offset, "timeout": 30},
                timeout=40,
            )
            data = _telegram_response(response)
            updates = data.get("result", [])
            if not isinstance(updates, list):
                raise RuntimeError("Telegram result is not a list")

            for update in updates:
                if not isinstance(update, dict):
                    continue

                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = max(offset, update_id + 1)

                message = update.get("message")
                if not isinstance(message, dict):
                    continue

                chat = message.get("chat")
                if not isinstance(chat, dict):
                    continue

                incoming_chat_id = chat.get("id")
                if str(incoming_chat_id) != _allowed_chat_id:
                    continue

                text = message.get("text")
                if not isinstance(text, str):
                    continue

                handle_command(text)
        except Exception as exc:  # keep long-poll loop alive on transient errors
            _safe_error("TG poll error", exc)
            time.sleep(3)


def _load_runtime_credentials() -> None:
    global _telegram_token, _allowed_chat_id
    global _mqtt_host, _mqtt_username, _mqtt_secret

    raw_directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if not raw_directory:
        raise RuntimeError("CREDENTIALS_DIRECTORY is not set")

    directory = Path(raw_directory)
    _telegram_token = read_credential(directory, "telegram-token")
    _allowed_chat_id = read_credential(directory, "telegram-chat-id")
    _mqtt_host = read_credential(directory, "mqtt-host")
    _mqtt_username = read_credential(directory, "mqtt-username")
    _mqtt_secret = read_credential(directory, "mqtt-secret")


def _mqtt_network_loop(client: mqtt.Client) -> None:
    # Paho 1.6.x publish() does not wake loop_start()'s select wait. Keep the
    # same loop_forever network-thread model, but bound Telegram -> MQTT
    # command dispatch scheduling latency explicitly.
    client.loop_forever(
        timeout=MQTT_LOOP_TIMEOUT_S,
        retry_first_connection=True,
    )


def _start_mqtt() -> None:
    global _mqttc

    callback_api = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api is None:
        client = mqtt.Client()
        client.on_connect = on_connect_v1
    else:
        client = mqtt.Client(callback_api.VERSION2)
        client.on_connect = on_connect_v2

    client.username_pw_set(_mqtt_username, _mqtt_secret)
    client.on_message = on_message
    client.connect(_mqtt_host, MQTT_PORT, MQTT_KEEPALIVE)
    thread = threading.Thread(
        target=_mqtt_network_loop,
        args=(client,),
        name="balkons-mqtt",
        daemon=True,
    )
    thread.start()
    _mqttc = client


def main() -> int:
    try:
        _load_runtime_credentials()
        _start_mqtt()
        _start_telegram_sender()
    except Exception as exc:
        _safe_error("Startup error", exc)
        return 1

    print("Balkons bot started")
    tg_send("🤖 Balkona bots (RPi5) startēja")
    telegram_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
