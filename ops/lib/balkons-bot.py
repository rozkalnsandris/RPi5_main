#!/usr/bin/env python3
"""Telegram <-> MQTT bridge for the balcony irrigation controller.

Runtime-only values are read from systemd's $CREDENTIALS_DIRECTORY.
No credential value is accepted through argv, committed source, or a
secret-specific environment variable.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import requests

MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
T_CMD = "balkons/cmd"
T_OUT = "balkons/telegram_out"

_telegram_token = ""
_allowed_chat_id = ""
_mqtt_host = ""
_mqtt_username = ""
_mqtt_secret = ""
_mqttc: mqtt.Client | None = None


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


def tg_send(text: str) -> None:
    try:
        response = requests.post(
            _telegram_url("sendMessage"),
            data={"chat_id": _allowed_chat_id, "text": text},
            timeout=10,
        )
        _telegram_response(response)
    except Exception as exc:  # bounded loop must survive transient API failures
        _safe_error("TG send error", exc)


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


def _publish_command(payload: str) -> None:
    if _mqttc is None:
        print("MQTT client unavailable", file=sys.stderr)
        return
    info = _mqttc.publish(T_CMD, payload)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"MQTT publish failed rc={info.rc}", file=sys.stderr)


def handle_command(text: str) -> None:
    text = text.strip()

    if text == "/laist":
        _publish_command("laist")
    elif text.startswith("/laist_"):
        _publish_command(f"laist_{text[7:]}")
    elif text == "/stop":
        _publish_command("stop")
    elif text == "/mitrums":
        _publish_command("mitrums")
    elif text == "/statuss":
        _publish_command("statuss")
    elif text == "/raw":
        _publish_command("raw")
    elif text == "/start":
        tg_send(
            "🌱 Balkona Laistīšana\n\n"
            "/laist — 30 sek\n"
            "/laist_2 — 2 min\n"
            "/stop — apturēt\n"
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
    client.loop_start()
    _mqttc = client


def main() -> int:
    try:
        _load_runtime_credentials()
        _start_mqtt()
    except Exception as exc:
        _safe_error("Startup error", exc)
        return 1

    print("Balkons bot started")
    tg_send("🤖 Balkona bots (RPi5) startēja")
    telegram_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
