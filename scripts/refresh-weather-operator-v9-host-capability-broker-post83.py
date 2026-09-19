#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v9_capability_broker_refresh_post83 as refresh

BASE_OPERATOR = ROOT / "scripts/refresh-weather-operator-v9-host-capability-broker.py"
CONTRACT = ROOT / "ops/deploy/weather-operator-v9-capability-broker-refresh-post83.json"


def _load_base_operator():
    spec = importlib.util.spec_from_file_location("weather_v9_broker_refresh_base", BASE_OPERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("base broker-refresh operator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.refresh = refresh
    module.CONTRACT = CONTRACT
    return module


base = _load_base_operator()


def main() -> int:
    parser = argparse.ArgumentParser(description="Weather v9 post-#83 capability broker refresh")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = base.apply() if args.apply else base.preflight()
    result["schema"] = (
        "rozkalns.rpi5-main.weather-operator-v9-capability-broker-refresh-post83-receipt.v1"
        if args.apply
        else "rozkalns.rpi5-main.weather-operator-v9-capability-broker-refresh-post83-preflight.v1"
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (base.CapabilityBrokerRefreshOperatorError, refresh.WeatherV9CapabilityBrokerRefreshError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "schema": "rozkalns.rpi5-main.weather-operator-v9-capability-broker-refresh-post83-receipt.v1",
                    "result": "FAIL_CLOSED",
                    "reason": str(exc),
                    "automatic_retry": False,
                    "automatic_cleanup": False,
                    "automatic_rollback": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise SystemExit(78)
