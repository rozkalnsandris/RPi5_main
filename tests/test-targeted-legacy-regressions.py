#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/targeted_legacy_regressions.py"
spec = importlib.util.spec_from_file_location("targeted_legacy_regressions", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.normalize_base(None) is None
assert module.normalize_base("") is None
assert module.normalize_base("000000") is None
assert module.normalize_base("abc123") == "abc123"

assert module.select_groups(None) == (True, True)
assert module.select_groups(["README.md"]) == (False, False)
assert module.select_groups([".github/workflows/validate.yml"]) == (True, True)
assert module.select_groups(["ops/lib/deploy_executor/example.py"]) == (True, True)
assert module.select_groups(["tests/hermes-deals-runner-smoke-example.py"]) == (True, False)
assert module.select_groups(["scripts/rpi5_deploy.py"]) == (False, True)
assert module.select_groups(["WeatherNext/example.py"]) == (False, True)
assert module.select_groups(["tests/test-WeAtHeRnExT-example.py"]) == (False, False)

print("Targeted legacy regression selector: PASS")
