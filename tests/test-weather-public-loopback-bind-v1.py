"""Source-only guard for the Weather PUBLIC SIMPLE-DEPLOY loopback binding (#915)."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST_COMPOSE = ROOT / "ops/deploy/simple-deploy-compose/rozkalns-weather-public.yml"
TARGETS = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
PRIVATE_HOME_BASELINE = (
    ROOT / "ops/deploy/baselines/simple-deploy-targets-weather-private-home-v1.json"
)
INGRESS_REGISTRY = ROOT / "ops/contracts/ingress-registry-v1.json"
WEATHER_ALIAS = "rozkalns-weather-public-rpi5"
EXPECTED_PUBLISH = "127.0.0.1:${WEATHER_PORT:-9180}:8000"


def _weather_block(compose: str) -> str:
    match = re.search(
        r"(?ms)^  weather:\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n|^volumes:\n|\\Z)",
        compose,
    )
    if match is None:
        raise AssertionError("missing fixed weather service")
    return match.group("body")


def _published_ports(compose: str) -> list[str]:
    match = re.search(
        r"(?m)^    ports:\n(?P<ports>(?:^      - .*\n)+)",
        _weather_block(compose),
    )
    if match is None:
        raise AssertionError("missing fixed weather publish block")
    ports = re.findall(r'^      - "([^"]+)"$', match.group("ports"), re.MULTILINE)
    if len(ports) != len(match.group("ports").splitlines()):
        raise AssertionError("unexpected published-port syntax")
    return ports


class WeatherPublicLoopbackBindTests(unittest.TestCase):
    def test_host_weather_publish_is_exact_loopback(self) -> None:
        compose = HOST_COMPOSE.read_text(encoding="utf-8")
        self.assertEqual(_published_ports(compose), [EXPECTED_PUBLISH])
        self.assertNotIn("0.0.0.0:", _weather_block(compose))
        self.assertNotIn("[::]:", _weather_block(compose))

    def test_old_and_wildcard_bindings_are_rejected(self) -> None:
        compose = HOST_COMPOSE.read_text(encoding="utf-8")
        self.assertEqual(_published_ports(compose), [EXPECTED_PUBLISH])
        for unsafe in (
            "${WEATHER_PORT:-9180}:8000",
            "0.0.0.0:${WEATHER_PORT:-9180}:8000",
            "[::]:${WEATHER_PORT:-9180}:8000",
            "localhost:${WEATHER_PORT:-9180}:8000",
        ):
            with self.subTest(unsafe=unsafe):
                candidate = compose.replace(
                    f'      - "{EXPECTED_PUBLISH}"', f'      - "{unsafe}"'
                )
                self.assertNotEqual(_published_ports(candidate), [EXPECTED_PUBLISH])

    def test_registry_hash_and_baseline_are_exact(self) -> None:
        targets = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"]
        weather = next(target for target in targets if target["target_alias"] == WEATHER_ALIAS)
        self.assertEqual(weather["compose"]["file"], HOST_COMPOSE.name)
        self.assertEqual(weather["compose"]["project"], "rozkalns-weather-public")
        self.assertEqual(weather["compose"]["service"], "weather")
        digest = hashlib.sha256(HOST_COMPOSE.read_bytes()).hexdigest()
        self.assertEqual(weather["compose"]["file_sha256"], digest)
        baseline = json.loads(PRIVATE_HOME_BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(
            baseline["targets"][0]["compose"]["file_sha256"], digest
        )
        self.assertEqual(weather["persistent_volumes"], ["weather_data"])
        self.assertEqual(weather["health"]["liveness_url"], "http://127.0.0.1:9180/health")
        self.assertEqual(weather["health"]["readiness_url"], "http://127.0.0.1:9180/ready")

    def test_private_home_and_digest_override_contracts_preserved(self) -> None:
        compose = HOST_COMPOSE.read_text(encoding="utf-8")
        block = _weather_block(compose)
        self.assertIn(
            "/etc/rozkalns-simple-deployer/private/rozkalns-weather-private-home.env",
            block,
        )
        self.assertIn("WEATHER_RUNTIME_MODE: private-home", block)
        self.assertIn("      - weather_data:/app/data", block)
        self.assertIn("http://127.0.0.1:8000/ready", block)
        self.assertIn("generic RPi5 deployer's frozen exact image@sha256 digest override", compose)
        self.assertIn('profiles: ["bootstrap"]', compose)
        self.assertIn('profiles: ["jobs"]', compose)
        self.assertIn('profiles: ["checks"]', compose)

    def test_ingress_registry_still_requires_public_loopback(self) -> None:
        ingress = json.loads(INGRESS_REGISTRY.read_text(encoding="utf-8"))
        item = next(
            service for service in ingress["services"]
            if service["service_id"] == "weather-public"
        )
        self.assertEqual(item["hostname"], "weather.rozkalns.net")
        self.assertEqual(item["zone"], "PUBLIC")
        self.assertEqual(item["desired_origin_class"], "loopback")
        self.assertEqual(item["access_class"], "NONE")
        self.assertFalse(item["access_required"])
        self.assertEqual(item["lan_break_glass"], "forbidden")


if __name__ == "__main__":
    unittest.main()
