#!/usr/bin/env python3
"""Offline sender regression tests; never connect to MQTT or Telegram."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import queue
import tempfile
import threading
import time
import types
import unittest
import unittest.mock
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "ops/lib/balkons-bot.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)
FUNCTION_NAMES = {
    "_send_telegram_now", "tg_send", "_telegram_sender_loop",
    "_start_telegram_sender", "_mqtt_notifications_enabled",
    "on_message", "_strict_json_object",
    "_connected", "_subscription_acknowledged", "on_subscribe_v1",
    "on_subscribe_v2",
    "_safety_state_max_age_s", "_manual_watering_admission",
    "_publish_command", "_publish_command_with_feedback",
    "_handle_manual_watering", "handle_command",
}
SELECTED = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTION_NAMES]
assert {n.name for n in SELECTED} == FUNCTION_NAMES
FUNCTIONS = compile(ast.fix_missing_locations(ast.Module(body=SELECTED, type_ignores=[])), str(SOURCE), "exec")


class BridgeTests(unittest.TestCase):
    def bridge(self, post=None, mqtt_rc=0):
        errors = []
        if post is None:
            post = lambda *args, **kwargs: object()
        outbound = queue.Queue(maxsize=16)
        publish_calls = []
        subscribe_calls = []

        class FakeMqtt:
            def subscribe(self, topic):
                subscribe_calls.append(topic)
                return (0, 19)

            def publish(self, *args, **kwargs):
                publish_calls.append((args, kwargs))
                return types.SimpleNamespace(rc=mqtt_rc)

        ns = {
            "queue": queue,
            "time": time,
            "threading": threading,
            "sys": __import__("sys"),
            "json": json,
            "os": os,
            "Path": Path,
            "requests": types.SimpleNamespace(post=post),
            "mqtt": types.SimpleNamespace(MQTT_ERR_SUCCESS=0),
            "_mqtt_subscribe_pending_mid": None,
            "T_OUT": "balkons/telegram_out",
            "_subscribe_calls": subscribe_calls,
            "_mqttc": FakeMqtt(),
            "_telegram_url": lambda method: "https://example.invalid/" + method,
            "_telegram_response": lambda response: {"ok": True},
            "_safe_error": lambda prefix, exc: errors.append((prefix, type(exc).__name__)),
            "_allowed_chat_id": "test-only",
            "_outbound_messages": outbound,
            "TELEGRAM_SLOW_SEND_S": 1.0,
            "T_CMD": "balkons/cmd",
            "SAFETY_STATE_SCHEMA": "rozkalns.balcony-watering-safety.v1",
            "SAFETY_STATE_DEFAULT_MAX_AGE_S": 21600,
            "SAFETY_STATE_MAX_BYTES": 4096,
            "SAFETY_STATE_KEYS": {
                "schema", "generated_at_epoch", "decision", "frost_blocked",
                "sensor_total", "sensor_degraded_count", "sensor_coverage_ok",
                "already_watered_today",
            },
        }
        exec(FUNCTIONS, ns)
        return ns, outbound, publish_calls, errors

    def test_mqtt_callback_only_enqueues_without_http(self):
        def forbidden_post(*args, **kwargs):
            self.fail("HTTP must never run in MQTT callback")
        ns, outbound, _, _ = self.bridge(forbidden_post)
        ns["on_message"](None, None, types.SimpleNamespace(payload=b"sensor reading"))
        self.assertEqual(outbound.qsize(), 1)
        item = outbound.get_nowait()
        self.assertEqual(item[0], "sensor reading")
        self.assertEqual(item[2], "mqtt")

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

    def test_notification_forwarding_default_preserves_existing_bridge(self):
        ns, outbound, _, _ = self.bridge()
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(ns["_mqtt_notifications_enabled"]())
            with contextlib.redirect_stderr(io.StringIO()):
                ns["_connected"](ns["_mqttc"], 0)
            self.assertEqual(ns["_subscribe_calls"], ["balkons/telegram_out"])
            ns["on_message"](None, None, types.SimpleNamespace(payload=b"normal"))
        self.assertEqual(outbound.get_nowait()[0], "normal")

    def test_opted_out_notifications_do_not_block_stop_command(self):
        ns, outbound, publishes, _ = self.bridge()
        with unittest.mock.patch.dict(os.environ, {"BALKONS_MQTT_TELEGRAM_FORWARD": "0"}):
            with contextlib.redirect_stderr(io.StringIO()) as log:
                ns["_connected"](ns["_mqttc"], 0)
            self.assertIn("MQTT notification forwarding disabled", log.getvalue())
            self.assertFalse(ns["_mqtt_notifications_enabled"]())
            self.assertEqual(ns["_subscribe_calls"], [])
            self.assertIsNone(ns["_mqtt_subscribe_pending_mid"])
            # Even an unexpected queued callback cannot double-send a message.
            ns["on_message"](None, None, types.SimpleNamespace(payload=b"not forwarded"))
            self.assertEqual(outbound.qsize(), 0)
            ns["handle_command"]("/stop")
        self.assertEqual([item[0] for item in publishes], [("balkons/cmd", "stop")])

    def test_invalid_forwarding_configuration_fails_closed(self):
        for value in ("false", "true", "1 ", "", "2"):
            with self.subTest(value=value):
                ns, outbound, _, _ = self.bridge()
                with unittest.mock.patch.dict(
                    os.environ, {"BALKONS_MQTT_TELEGRAM_FORWARD": value}
                ):
                    with contextlib.redirect_stderr(io.StringIO()):
                        ns["_connected"](ns["_mqttc"], 0)
                    ns["on_message"](
                        None, None, types.SimpleNamespace(payload=b"no duplicate")
                    )
                self.assertEqual(ns["_subscribe_calls"], [])
                self.assertTrue(outbound.empty())

    def test_explicit_forwarding_enabled_keeps_legacy_behavior(self):
        ns, outbound, _, _ = self.bridge()
        with unittest.mock.patch.dict(
            os.environ, {"BALKONS_MQTT_TELEGRAM_FORWARD": "1"}
        ):
            with contextlib.redirect_stderr(io.StringIO()):
                ns["_connected"](ns["_mqttc"], 0)
            ns["on_message"](None, None, types.SimpleNamespace(payload=b"enabled"))
        self.assertEqual(ns["_subscribe_calls"], ["balkons/telegram_out"])
        self.assertEqual(outbound.get_nowait()[0], "enabled")

    def test_subscribe_request_not_counted_as_broker_ack(self):
        ns, _, _, _ = self.bridge()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            ns["_connected"](ns["_mqttc"], 0)
        self.assertEqual(ns["_subscribe_calls"], ["balkons/telegram_out"])
        self.assertEqual(ns["_mqtt_subscribe_pending_mid"], 19)
        self.assertIn("MQTT connected", stderr.getvalue())
        self.assertNotIn("MQTT SUBACK accepted", stderr.getvalue())
        with contextlib.redirect_stderr(stderr):
            ns["on_subscribe_v1"](None, None, 19, [0])
        self.assertIn("MQTT SUBACK accepted", stderr.getvalue())
        self.assertIsNone(ns["_mqtt_subscribe_pending_mid"])

    def test_v2_suback_requires_matching_mid_and_success_reason(self):
        ns, _, _, _ = self.bridge()
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            ns["_connected"](ns["_mqttc"], 0)
            ns["on_subscribe_v2"](
                None, None, 18, [types.SimpleNamespace(value=0)], None
            )
            self.assertEqual(ns["_mqtt_subscribe_pending_mid"], 19)
            ns["on_subscribe_v2"](
                None, None, 19, [types.SimpleNamespace(value=0)], None
            )
        lines = output.getvalue().splitlines()
        self.assertIn("MQTT SUBACK unmatched", lines)
        self.assertIn("MQTT SUBACK accepted", lines)
        self.assertIsNone(ns["_mqtt_subscribe_pending_mid"])

    def test_suback_rejection_unknown_and_reconnect_clear_pending(self):
        ns, _, _, _ = self.bridge()
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            ns["_connected"](ns["_mqttc"], 0)
            ns["on_subscribe_v1"](None, None, 19, [128])
            ns["_connected"](ns["_mqttc"], 0)
            ns["on_subscribe_v2"](None, None, 19, [], None)
            ns["_connected"](ns["_mqttc"], 0)
            ns["on_subscribe_v2"](
                None, None, 19, [types.SimpleNamespace(value=0x80)], None
            )
            ns["_connected"](ns["_mqttc"], 0)
            ns["_connected"](ns["_mqttc"], 5)
            ns["on_subscribe_v1"](None, None, 19, [0])
        lines = output.getvalue().splitlines()
        self.assertEqual(lines.count("MQTT SUBACK rejected"), 2)
        self.assertIn("MQTT SUBACK unknown", lines)
        self.assertIn("MQTT connection rejected", lines)
        self.assertIn("MQTT SUBACK unmatched", lines)
        self.assertNotIn("MQTT SUBACK accepted", lines)
        self.assertIsNone(ns["_mqtt_subscribe_pending_mid"])

    def test_telegram_api_outcomes_distinguish_local_and_mqtt_provenance(self):
        ns, outbound, _, _ = self.bridge()
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            ns["_start_telegram_sender"]()
            ns["on_message"](
                None, None, types.SimpleNamespace(payload=b"private MQTT message")
            )
            ns["tg_send"]("private local message")
            deadline = time.monotonic() + 2
            while outbound.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(outbound.unfinished_tasks, 0)
        lines = output.getvalue().splitlines()
        self.assertIn("TG API outcome source=mqtt ok=1", lines)
        self.assertIn("TG API outcome source=local ok=1", lines)
        self.assertNotIn("private", output.getvalue())
        self.assertNotIn("balkons/telegram_out", output.getvalue())
        self.assertNotIn("test-only", output.getvalue())

    def test_failed_mqtt_send_reports_fixed_category_without_retry(self):
        calls = []
        def fails(*args, **kwargs):
            calls.append(1)
            raise TimeoutError("token-bearing URL never to be logged")
        ns, outbound, _, errors = self.bridge(fails)
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            ns["_start_telegram_sender"]()
            ns["on_message"](
                None, None, types.SimpleNamespace(payload=b"private response")
            )
            deadline = time.monotonic() + 2
            while outbound.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(len(calls), 1)
        self.assertEqual(errors, [("TG send error", "TimeoutError")])
        self.assertIn("TG API outcome source=mqtt ok=0", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_observability_is_event_only_without_extra_network_calls(self):
        self.assertIn('setattr(client, "on_subscribe", on_subscribe_v1)', TEXT)
        self.assertIn('setattr(client, "on_subscribe", on_subscribe_v2)', TEXT)
        self.assertEqual(TEXT.count("client.subscribe(T_OUT)"), 1)
        self.assertEqual(TEXT.count("requests.post("), 1)
        self.assertNotIn("client.publish(T_OUT", TEXT)

    def _write_safety(self, directory, **overrides):
        state = {
            "schema": "rozkalns.balcony-watering-safety.v1",
            "generated_at_epoch": int(time.time()),
            "decision": "manual_permit",
            "frost_blocked": False,
            "sensor_total": 10,
            "sensor_degraded_count": 0,
            "sensor_coverage_ok": True,
            "already_watered_today": False,
        }
        state.update(overrides)
        path = Path(directory) / "manual-safety-v1.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        return path

    def test_manual_watering_requires_fresh_permitting_state(self):
        ns, outbound, published, _ = self.bridge()
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_safety(directory)
            with unittest.mock.patch.dict(
                os.environ,
                {"BALCONY_SAFETY_STATE_FILE": str(path)},
                clear=False,
            ):
                ns["handle_command"]("/laist")
        self.assertEqual(published, [(("balkons/cmd", "laist"), {})])
        self.assertEqual(outbound.qsize(), 0)

    def test_manual_watering_expands_neutral_home_safety_path(self):
        ns, outbound, published, _ = self.bridge()
        with tempfile.TemporaryDirectory() as home:
            state_dir = Path(home) / ".local/state/balcony-watering-autumn"
            state_dir.mkdir(parents=True)
            self._write_safety(state_dir)
            with unittest.mock.patch.dict(
                os.environ,
                {
                    "HOME": home,
                    "BALCONY_SAFETY_STATE_FILE":
                        "~/.local/state/balcony-watering-autumn/manual-safety-v1.json",
                },
                clear=False,
            ):
                ns["handle_command"]("/laist")
        self.assertEqual(published, [(("balkons/cmd", "laist"), {})])
        self.assertEqual(outbound.qsize(), 0)

    def test_manual_watering_blocks_frost_stale_and_missing_state(self):
        ns, outbound, published, _ = self.bridge()
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_safety(
                directory,
                decision="block_frost",
                frost_blocked=True,
            )
            with unittest.mock.patch.dict(
                os.environ,
                {"BALCONY_SAFETY_STATE_FILE": str(path)},
                clear=False,
            ):
                ns["handle_command"]("/laist_2")
            self.assertEqual(published, [])
            self.assertIn("sala risks", outbound.get_nowait()[0])

            path = self._write_safety(
                directory,
                generated_at_epoch=int(time.time()) - 21601,
            )
            with unittest.mock.patch.dict(
                os.environ,
                {"BALCONY_SAFETY_STATE_FILE": str(path)},
                clear=False,
            ):
                ns["handle_command"]("/laist")
            self.assertIn("novecojusi", outbound.get_nowait()[0])

            path.unlink()
            with unittest.mock.patch.dict(
                os.environ,
                {"BALCONY_SAFETY_STATE_FILE": str(path)},
                clear=False,
            ):
                ns["handle_command"]("/laist")
            self.assertIn("nav pieejams", outbound.get_nowait()[0])

            path.write_text("[]", encoding="utf-8")
            with unittest.mock.patch.dict(
                os.environ,
                {"BALCONY_SAFETY_STATE_FILE": str(path)},
                clear=False,
            ):
                ns["handle_command"]("/laist")
            self.assertIn("nav derīgs", outbound.get_nowait()[0])

            path = self._write_safety(
                directory,
                decision="block_sensor_coverage",
                sensor_degraded_count=3,
                sensor_coverage_ok=False,
            )
            with unittest.mock.patch.dict(
                os.environ,
                {"BALCONY_SAFETY_STATE_FILE": str(path)},
                clear=False,
            ):
                ns["handle_command"]("/laist")
            self.assertIn("nepietiek derīgu mitruma sensoru", outbound.get_nowait()[0])

    def test_stop_bypasses_manual_watering_gate(self):
        ns, _, published, _ = self.bridge()
        with unittest.mock.patch.dict(
            os.environ,
            {"BALCONY_SAFETY_STATE_FILE": "/does/not/exist"},
            clear=False,
        ):
            ns["handle_command"]("/stop")
        self.assertEqual(published, [(("balkons/cmd", "stop"), {})])

    def test_mqtt_publish_failure_feedback_is_one_shot(self):
        ns, outbound, published, _ = self.bridge(mqtt_rc=4)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_safety(directory)
            with unittest.mock.patch.dict(
                os.environ,
                {"BALCONY_SAFETY_STATE_FILE": str(path)},
                clear=False,
            ):
                ns["handle_command"]("/laist")
        self.assertEqual(published, [(("balkons/cmd", "laist"), {})])
        self.assertEqual(outbound.qsize(), 1)
        self.assertIn("netika nosūtīta", outbound.get_nowait()[0])

    def test_non_watering_command_publish_contract_unchanged(self):
        ns, _, published, _ = self.bridge()
        ns["handle_command"]("/mitrums")
        ns["handle_command"]("/stop")
        self.assertEqual(
            published,
            [
                (("balkons/cmd", "mitrums"), {}),
                (("balkons/cmd", "stop"), {}),
            ],
        )

    def test_worker_starts_before_polling(self):
        main = TEXT.split("def main() -> int:", 1)[1]
        self.assertLess(main.index("_start_mqtt()"), main.index("_start_telegram_sender()"))
        self.assertLess(main.index("_start_telegram_sender()"), main.index("telegram_loop()"))


if __name__ == "__main__":
    unittest.main()
