#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-weather-v9-predecessor-bootstrap-capability.py"
BROKER_RELATIVE = "ops/bin/rozkalns-weather-v9-predecessor-bootstrap-broker"
RECOVERY_RELATIVE = "ops/recovery/weather_v9_predecessor_state_bootstrap.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


installer = load(INSTALLER, "weather_v9_predecessor_bootstrap_installer_release_test")


class Tests(unittest.TestCase):
    def test_declared_release_imports_without_full_source_checkout(self):
        self.assertIn("ops/lib/deploy_executor/__init__.py", installer.RELEASE_FILES)
        self.assertNotIn("ops/lib/deploy_executor/protocol.py", installer.RELEASE_FILES)
        self.assertNotIn("ops/lib/deploy_executor/transport.py", installer.RELEASE_FILES)

        with tempfile.TemporaryDirectory() as td:
            release = Path(td) / "current"
            for relative in installer.RELEASE_FILES:
                source = ROOT / relative
                target = release / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())

            broker = release / BROKER_RELATIVE
            recovery = release / RECOVERY_RELATIVE
            package_root = release / "ops/lib/deploy_executor"
            script = f"""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys

broker_path = Path({str(broker)!r})
recovery_path = Path({str(recovery)!r})
package_root = Path({str(package_root)!r})

loader = SourceFileLoader("isolated_weather_v9_bootstrap_broker", str(broker_path))
spec = importlib.util.spec_from_loader(loader.name, loader)
if spec is None or spec.loader is None:
    raise RuntimeError("isolated broker spec unavailable")
broker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = broker
spec.loader.exec_module(broker)

package = sys.modules.get("deploy_executor")
if package is None or list(package.__path__) != [str(package_root)]:
    raise RuntimeError("broker did not install the isolated package view")
if "deploy_executor.protocol" in sys.modules or "deploy_executor.transport" in sys.modules:
    raise RuntimeError("normal deploy executor package initializer leaked into bootstrap runtime")

recovery_spec = importlib.util.spec_from_file_location(
    "isolated_weather_v9_predecessor_recovery", recovery_path
)
if recovery_spec is None or recovery_spec.loader is None:
    raise RuntimeError("isolated recovery spec unavailable")
recovery_module = importlib.util.module_from_spec(recovery_spec)
sys.modules[recovery_spec.name] = recovery_module
recovery_spec.loader.exec_module(recovery_module)
state_store = recovery_module._load_state_store()
if state_store.__name__ != "StateStore":
    raise RuntimeError("isolated StateStore import drifted")
if "deploy_executor.state" not in sys.modules:
    raise RuntimeError("isolated StateStore submodule was not loaded")
if "deploy_executor.protocol" in sys.modules or "deploy_executor.transport" in sys.modules:
    raise RuntimeError("StateStore import executed the normal package initializer")
print("PASS")
"""
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", script],
                cwd=td,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "PASS")


if __name__ == "__main__":
    unittest.main()
