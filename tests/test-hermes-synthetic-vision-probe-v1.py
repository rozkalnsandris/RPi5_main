"""Offline-only synthetic vision guard tests: no Hermes, host or network access."""

from __future__ import annotations

import base64
import importlib.util
import io
import socket
import struct
import unittest
import zlib
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ops/lib/hermes_synthetic_vision_probe_v1.py"
SPEC = importlib.util.spec_from_file_location("hermes_synthetic_vision_probe_v1", SRC)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def valid_envelope() -> dict:
    return {
        "media_refs": (mod.FIXTURE_REF,),
        "image_mode": mod.IMAGE_MODE,
        "provider": mod.PROVIDER,
        "model": mod.MODEL,
    }


class HermesSyntheticVisionProbeTests(unittest.TestCase):
    def test_fixture_is_deterministic_png_with_expected_colors(self) -> None:
        png = mod.synthetic_png()
        self.assertEqual(png, mod.synthetic_png())
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        stream = io.BytesIO(png[8:])
        image = bytearray()
        while (length_raw := stream.read(4)):
            (length,) = struct.unpack(">I", length_raw)
            kind = stream.read(4)
            payload = stream.read(length)
            stream.read(4)  # CRC
            if kind == b"IHDR":
                self.assertEqual(struct.unpack(">II", payload[:8]), (96, 96))
                self.assertEqual(payload[8:10], b"\x08\x02")
            if kind == b"IDAT":
                image.extend(zlib.decompress(payload))
        row_size = 1 + 96 * 3

        def pixel(x: int, y: int) -> bytes:
            self.assertEqual(image[y * row_size], 0)
            offset = y * row_size + 1 + x * 3
            return bytes(image[offset: offset + 3])

        self.assertEqual(pixel(48, 48), bytes((230, 28, 42)))
        self.assertEqual(pixel(0, 0), bytes((23, 80, 184)))

    def test_request_is_fixed_free_image_no_fallback(self) -> None:
        request = mod.synthetic_request()
        self.assertEqual(request["model"], "nvidia/nemotron-3.5-super-vl:free")
        self.assertEqual(request["max_tokens"], 100)
        parts = request["messages"][0]["content"]
        self.assertEqual(parts[0]["text"], mod.PROMPT)
        encoded = parts[1]["image_url"]["url"]
        self.assertTrue(encoded.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(encoded.split(",", 1)[1]), mod.synthetic_png())
        self.assertEqual(request["extra_body"]["provider"]["max_price"],
                         {"prompt": 0, "completion": 0, "image": 0, "request": 0})
        self.assertIs(request["extra_body"]["provider"]["allow_fallbacks"], False)

    def test_one_callback_success_without_file_io_or_network(self) -> None:
        gate = mod.SingleUseSyntheticProbe()
        sender = Mock(return_value=" RED \n")
        with patch("builtins.open", side_effect=AssertionError("UNEXPECTED_FILE_IO")), (
            patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK"))):
            result = gate.run(**valid_envelope(), send=sender)
        self.assertEqual(result, {
            "status": "OFFLINE_PASS", "color": "RED", "callback_attempts": 1,
        })
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(sender.call_args.args[0], mod.synthetic_request())
        self.assertEqual(gate.callback_attempts, 1)
        with self.assertRaisesRegex(mod.ProbeRejected, "ALREADY_ATTEMPTED"):
            gate.run(**valid_envelope(), send=sender)
        self.assertEqual(sender.call_count, 1)

    def test_rejects_non_synthetic_and_fanout_before_dispatch(self) -> None:
        rejected = [
            (),
            ("/tmp/photo.png",),
            ("https://example.invalid/picture.png",),
            ("data:image/png;base64,aaaa",),
            (mod.FIXTURE_REF, mod.FIXTURE_REF),
            [mod.FIXTURE_REF],
            ("synthetic:other",),
        ]
        for value in rejected:
            with self.subTest(media_refs=value):
                gate = mod.SingleUseSyntheticProbe()
                sender = Mock(return_value="RED")
                with self.assertRaisesRegex(mod.ProbeRejected, "FIXTURE_ONLY"):
                    gate.run(**{**valid_envelope(), "media_refs": value}, send=sender)
                sender.assert_not_called()
                self.assertEqual(gate.callback_attempts, 0)

    def test_native_main_wrong_model_or_provider_rejected(self) -> None:
        cases = [
            {"image_mode": "native"},
            {"provider": "local"},
            {"model": "nvidia/nemotron-3.5-super-vl"},
            {"model": "openrouter/free"},
            {"model": "google/gemma-4-31b-it:free"},
        ]
        for case in cases:
            with self.subTest(case=case):
                gate = mod.SingleUseSyntheticProbe()
                sender = Mock(return_value="RED")
                with self.assertRaisesRegex(mod.ProbeRejected, "ROUTE_MISMATCH"):
                    gate.run(**{**valid_envelope(), **case}, send=sender)
                sender.assert_not_called()
                self.assertEqual(gate.callback_attempts, 0)

    def test_missing_callback_does_not_consume_attempt(self) -> None:
        gate = mod.SingleUseSyntheticProbe()
        with self.assertRaisesRegex(mod.ProbeRejected, "NO_OFFLINE_CALLBACK"):
            gate.run(**valid_envelope(), send=None)
        self.assertEqual(gate.callback_attempts, 0)

    def test_failure_and_timeout_consume_single_attempt(self) -> None:
        for exception in (RuntimeError("provider failed"), TimeoutError("timeout")):
            with self.subTest(exception=type(exception).__name__):
                gate = mod.SingleUseSyntheticProbe()
                sender = Mock(side_effect=exception)
                with self.assertRaisesRegex(mod.ProbeDispatchFailed, "CALLBACK_FAILED"):
                    gate.run(**valid_envelope(), send=sender)
                self.assertEqual(sender.call_count, 1)
                self.assertEqual(gate.callback_attempts, 1)
                with self.assertRaisesRegex(mod.ProbeRejected, "ALREADY_ATTEMPTED"):
                    gate.run(**valid_envelope(), send=sender)
                self.assertEqual(sender.call_count, 1)

    def test_empty_wrong_mixed_response_no_retry(self) -> None:
        for reply in ("", "BLUE", "RED GREEN", None, {"answer": "RED"}):
            with self.subTest(reply=reply):
                gate = mod.SingleUseSyntheticProbe()
                sender = Mock(return_value=reply)
                with self.assertRaisesRegex(mod.ProbeDispatchFailed, "UNEXPECTED_RESPONSE"):
                    gate.run(**valid_envelope(), send=sender)
                self.assertEqual(sender.call_count, 1)
                with self.assertRaisesRegex(mod.ProbeRejected, "ALREADY_ATTEMPTED"):
                    gate.run(**valid_envelope(), send=sender)
                self.assertEqual(sender.call_count, 1)

    def test_reentrant_dispatch_rejected(self) -> None:
        gate = mod.SingleUseSyntheticProbe()
        attempts = []

        def sender(_: dict) -> str:
            attempts.append("sent")
            with self.assertRaisesRegex(mod.ProbeRejected, "ALREADY_ATTEMPTED"):
                gate.run(**valid_envelope(), send=lambda request: "RED")
            return "RED"

        result = gate.run(**valid_envelope(), send=sender)
        self.assertEqual(result["status"], "OFFLINE_PASS")
        self.assertEqual(attempts, ["sent"])

    def test_makefile_runs_probe_tests(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("python3 ./tests/test-hermes-synthetic-vision-probe-v1.py", makefile)


if __name__ == "__main__":
    unittest.main()
