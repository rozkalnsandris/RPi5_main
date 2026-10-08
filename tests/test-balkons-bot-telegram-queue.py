#!/usr/bin/env python3
"""Offline sender regression tests; never connect to MQTT or Telegram."""
from __future__ import annotations

import ast
import contextlib
import io
import queue
import threading
import time
import types
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "ops/lib/balkons-bot.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)
FUNCTION_NAMES = {
    "_send_telegram_now", "tg_send", "_telegram_sender_loop",
    "_start_telegram_sender", "on_message", "_publish_command", "handle_command",
}
SELECTED = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTION_NAMES]
assert {n.name for n in SELECTED} == FUNCTION_NAMES
FUNCTIONS = compile(ast.fix_missing_locations(ast.Module(body=SELECTED, type_ignores=[])), str(SOURCE), "exec")


class BridgeTests(unittest.TestCase):
    def bridge(self, post=None):
        errors = []
        if post is None:
            post = lambda *args, **kwargs: object()
        outbound = queue.Queue(maxsize=16)
        publish_calls = []

        class FakeMqtt:
            def publish(self, *args, **kwargs):
                publish_calls.append((args, kwargs))
                return types.SimpleNamespace(rc=0)

        ns = {
            "queue": queue,
            "time": time,
            "threading": threading,
            "sys": __import__("sys"),
            "requests": types.SimpleNamespace(post=post),
            "mqtt": types.SimpleNamespace(MQTT_ERR_SUCCESS=0),
            "_mqttc": FakeMqtt(),
            "_telegram_url": lambda method: "https://example.invalid/" + method,
            "_telegram_response": lambda response: {"ok": True},
            "_safe_error": lambda prefix, exc: errors.append((prefix, type(exc).__name__)),
            "_allowed_chat_id": "test-only",
            "_outbound_messages": outbound,
            "TELEGRAM_SLOW_SEND_S": 1.0,
            "T_CMD": "balkons/cmd",
        }
        exec(FUNCTIONS, ns)
        return ns, outbound, publish_calls, errors

    def test_mqtt_callback_only_enqueues_without_http(self):
        def forbidden_post(*args, **kwargs):
            self.fail("HTTP must never run in MQTT callback")
        ns, outbound, _, _ = self.bridge(forbidden_post)
        ns["on_message"](None, None, types.SimpleNamespace(payload=b"sensor reading"))
        self.assertEqual(outbound.qsize(), 1)
        self.assertEqual(outbound.get_nowait()[0], "sensor reading")

    def test_slow_http_does_not_block_next_mqtt_callback(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def slow_post(url, data, timeout):
            calls.append((url, data["text"], timeout))
            entered.set()
            release.wait(2)
            return object()

        ns, outbound, _, _ = self.bridge(slow_post)
        ns["_start_telegram_sender"]()
        try:
            ns["tg_send"]("first")
            self.assertTrue(entered.wait(1), "sender did not begin HTTP")
            start = time.monotonic()
            ns["on_message"](None, None, types.SimpleNamespace(payload=b"mitrums reply"))
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertEqual(outbound.qsize(), 1)
        finally:
            release.set()

        deadline = time.monotonic() + 2
        while outbound.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(outbound.unfinished_tasks, 0)
        self.assertEqual([item[1] for item in calls], ["first", "mitrums reply"])
        self.assertEqual([item[2] for item in calls], [10, 10])

    def test_queue_is_bounded_and_does_not_log_payload(self):
        ns, outbound, _, _ = self.bridge()
        for index in range(16):
            ns["tg_send"](f"state {index}")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            ns["tg_send"]("private payload must not appear in journal")
        self.assertEqual(outbound.qsize(), 16)
        self.assertEqual(outbound.get_nowait()[0], "state 0")
        self.assertIn("queue full", stderr.getvalue())
        self.assertNotIn("private payload", stderr.getvalue())

    def test_failed_http_is_not_retried_or_logged_with_url(self):
        attempts = []

        def fail_post(*args, **kwargs):
            attempts.append(1)
            raise TimeoutError("secret-bearing URL")
        ns, outbound, _, errors = self.bridge(fail_post)
        ns["_start_telegram_sender"]()
        ns["tg_send"]("report")
        deadline = time.monotonic() + 2
        while outbound.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(outbound.unfinished_tasks, 0)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(errors, [("TG send error", "TimeoutError")])

    def test_command_publish_contract_unchanged(self):
        ns, _, published, _ = self.bridge()
        ns["handle_command"]("/mitrums")
        ns["handle_command"]("/stop")
        ns["handle_command"]("/laist")
        self.assertEqual(
            published,
            [
                (("balkons/cmd", "mitrums"), {}),
                (("balkons/cmd", "stop"), {}),
                (("balkons/cmd", "laist"), {}),
            ],
        )

    def test_worker_starts_before_polling(self):
        main = TEXT.split("def main() -> int:", 1)[1]
        self.assertLess(main.index("_start_mqtt()"), main.index("_start_telegram_sender()"))
        self.assertLess(main.index("_start_telegram_sender()"), main.index("telegram_loop()"))


if __name__ == "__main__":
    unittest.main()
