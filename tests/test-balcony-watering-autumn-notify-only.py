#!/usr/bin/env python3
"""Legacy 11:00 watering notification-only parity tests: fully offline (#1495)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "ops/bin/balcony-watering-autumn-notify-only"
CURRENT = ROOT / "ops/bin/balcony-watering-autumn"
BRIDGE = ROOT / "ops/lib/balkons-bot.py"
MANIFEST = ROOT / "ci/validate-groups.json"
OLD_SHA = "86972a10bd457abb6350e2f924d7c3bcc54139af322f335707f51e1e440ac60b"
CURRENT_SHA = "0117ab6230c5b388d71fed2aebfa072f48a1a891a9608de12bfd6bc5b139e693"
CANDIDATE_SHA = "7c993c5e0fdffdcb405b57aebad2be65a133be17caf13f16492fde6f12bc45b1"
ORIGINAL_BLOCK = "# Message policy: real watering, normal skip, error, frost block and lock\n# contention. Deliver via the existing RPi5 notifications bot, not Hermes.\nsend_tg() {\n    if [[ \"$DRY_RUN\" == \"1\" ]]; then\n        log \"DRY-RUN telegram (suppressed): $1\"\n        return 0\n    fi\n\n    if [[ -z \"${TELEGRAM_TOKEN:-}\" || -z \"${CHAT_ID:-}\" ]]; then\n        return 0\n    fi\n\n    curl -s --max-time 15 -X POST \"https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage\" \\\n        -d \"chat_id=${CHAT_ID}\" \\\n        --data-urlencode \"text=$1\" >/dev/null 2>&1 || true\n}\n"
NOTIFICATION_BLOCK = "# Notifications go through existing HA MQTT -> Balkona bot bridge only.\n# Fixed notification-only topic; never duplicate Telegram credentials.\nsend_tg() {\n    if [[ \"$DRY_RUN\" == \"1\" ]]; then\n        log \"DRY-RUN notification (suppressed): $1\"\n        return 0\n    fi\n\n    local http_code\n    http_code=\"$(\n        printf '%s' \"$1\" |\n            python3 -c '\nimport json\nimport sys\njson.dump(\n    {\"topic\": \"balkons/telegram_out\", \"payload\": sys.stdin.read(), \"qos\": 0, \"retain\": False},\n    sys.stdout,\n    ensure_ascii=False,\n)\n' |\n            curl -s -o /dev/null -w '%{http_code}' --max-time 15 -X POST \\\n                \"${HASS_URL}/api/services/mqtt/publish\" \\\n                -H \"${AUTH_HEADER_NAME}: Bearer ${HASS_TOKEN}\" \\\n                -H \"Content-Type: application/json\" \\\n                --data-binary @- 2>/dev/null\n    )\" || http_code=\"000\"\n\n    if [[ \"$http_code\" == \"200\" ]]; then\n        log \"NOTIFY-MQTT: submitted to balcony bot bridge (Telegram receipt unconfirmed)\"\n    else\n        log \"NOTIFY-WARN: balcony bot MQTT publish failed (HTTP ${http_code})\"\n    fi\n}\n"


class NotificationOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = CANDIDATE.read_text(encoding="utf-8")

    def test_exact_historical_file_restored_by_reverting_one_block(self):
        self.assertEqual(self.content.count(NOTIFICATION_BLOCK), 1)
        self.assertEqual(self.content.count(ORIGINAL_BLOCK), 0)
        old = self.content.replace(NOTIFICATION_BLOCK, ORIGINAL_BLOCK).encode("utf-8")
        self.assertEqual(hashlib.sha256(old).hexdigest(), OLD_SHA)
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest(), CANDIDATE_SHA)

    def test_old_policy_stays_unchanged(self):
        self.assertIn("ACTIVE_SENSORS=(1 3 4 5 6 7 8 9 10 11 12 13)", self.content)
        self.assertIn("ACTIVE_SENSOR_COUNT=12", self.content)
        self.assertIn("ESP32_MAX_SECONDS=180", self.content)
        self.assertNotIn("MAX_DEGRADED", self.content)
        self.assertNotIn("manual-safety-v1.json", self.content)
        self.assertEqual(hashlib.sha256(CURRENT.read_bytes()).hexdigest(), CURRENT_SHA)

    def test_notification_dest_is_only_existing_bot_topic(self):
        self.assertIn('"topic": "balkons/telegram_out"', NOTIFICATION_BLOCK)
        self.assertIn('"qos": 0, "retain": False', NOTIFICATION_BLOCK)
        self.assertIn("/api/services/mqtt/publish", NOTIFICATION_BLOCK)
        self.assertIn("if [[ \"$DRY_RUN\" == \"1\" ]]", NOTIFICATION_BLOCK)
        for forbidden in ("api.telegram.org", "TELEGRAM_TOKEN", "CHAT_ID",
                          "balkons/cmd", "switch.turn_on", "switch.turn_off",
                          "mosquitto_pub", "telegram_bot.send_message"):
            self.assertNotIn(forbidden, NOTIFICATION_BLOCK)
        bot = BRIDGE.read_text(encoding="utf-8")
        self.assertIn('T_OUT = "balkons/telegram_out"', bot)
        self.assertIn("client.subscribe(T_OUT)", bot)

    def test_syntax_and_ci_registration(self):
        p = subprocess.run(["bash", "-n", str(CANDIDATE)],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 0)
        groups = json.loads(MANIFEST.read_text(encoding="utf-8"))["groups"]
        self.assertEqual(groups["balcony"].count(
            ["python3", "./tests/test-balcony-watering-autumn-notify-only.py"]), 1)

    def send_offline(self, msg: str, *, dry: bool = False,
                     status: str = "200") -> tuple[list[dict], str]:
        # Execute ONLY the exact extracted notifier; mock curl blocks network.
        with tempfile.TemporaryDirectory(prefix="balcony-notify-only-") as folder:
            root = Path(folder)
            capture, log, curl = root / "calls.jsonl", root / "log.txt", root / "curl"
            curl.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "record = {'args': sys.argv[1:], 'body': sys.stdin.read()}\n"
                "with Path(os.environ['CAPTURE']).open('a') as f:\n"
                "    f.write(json.dumps(record, ensure_ascii=False) + '\\n')\n"
                "print(os.environ['STATUS'], end='')\n", encoding="utf-8"
            )
            curl.chmod(0o700)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ.get("PATH", "/usr/bin"),
                       CAPTURE=str(capture), LOGFILE_TEST=str(log), STATUS=status)
            command = (
                "set -Eeuo pipefail\n"
                + ("DRY_RUN=1\n" if dry else "DRY_RUN=0\n")
                + "HASS_URL=https://example.invalid\n"
                + "HASS_TOKEN=offline-placeholder-not-secret\n"
                + "AUTH_HEADER_NAME=Authorization\n"
                + "log() { printf '%s\\n' \"$*\" >> \"$LOGFILE_TEST\"; }\n"
                + NOTIFICATION_BLOCK + "\nsend_tg \"$1\"\n"
            )
            p = subprocess.run(["bash", "-c", command, "offline", msg],
                               env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 0, "offline notifier failed")
            calls = [json.loads(x) for x in capture.read_text(encoding="utf-8").splitlines()] if capture.exists() else []
            logs = log.read_text(encoding="utf-8") if log.exists() else ""
            return calls, logs

    def test_single_bounded_notification_payload(self):
        msg = "💧 Nav laistīts — sals\nPārbaude 'quoted' \"again\""
        calls, logs = self.send_offline(msg)
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(calls[0]["body"]), {
            "topic": "balkons/telegram_out", "payload": msg, "qos": 0, "retain": False
        })
        self.assertEqual(calls[0]["args"].count(
            "https://example.invalid/api/services/mqtt/publish"), 1)
        self.assertIn("POST", calls[0]["args"])
        self.assertIn("--data-binary", calls[0]["args"])
        self.assertIn("NOTIFY-MQTT:", logs)

    def test_dry_run_sends_nothing(self):
        calls, logs = self.send_offline("dry", dry=True)
        self.assertEqual(calls, [])
        self.assertIn("DRY-RUN", logs)

    def test_rejected_http_never_retries(self):
        calls, logs = self.send_offline("safe", status="503")
        self.assertEqual(len(calls), 1)
        self.assertIn("NOTIFY-WARN:", logs)
        self.assertNotIn("NOTIFY-MQTT:", logs)


if __name__ == "__main__":
    unittest.main()
