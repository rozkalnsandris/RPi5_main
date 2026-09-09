from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ops/deploy/weather-public-runtime-helper-install.json"
ENTRYPOINT_SOURCE = ROOT / "ops/bin/rozkalns-weather-public-runtime-stage-helper"
EXECUTION_TEST = ROOT / "tests/test-deploy-executor-weather-public-execution.py"
DEDICATED_ROOT = "/usr/local/libexec/rozkalns-weather-public-runtime"
EXECUTABLE = "/usr/local/libexec/rozkalns-weather-public-runtime-stage-helper"
PACKAGE_ROOT = f"{DEDICATED_ROOT}/deploy_executor"
EXISTING_EXECUTOR_ROOT = "/usr/local/libexec/rozkalns-deploy-executor/deploy_executor"

EXPECTED_MODULES = {
    "adapters",
    "queue_normalizer",
    "registry",
    "protocol",
    "weather_public_runtime_adapter",
    "weather_public_runtime_bootstrap",
    "weather_public_runtime_preactivation",
    "weather_public_runtime_host_wiring",
    "weather_public_runtime_execution",
    "weather_public_runtime_candidate_materializer",
    "weather_public_runtime_stage_helper",
}


class WeatherHelperInstallLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.artifacts = cls.manifest["artifacts"]

    def test_manifest_is_exact_isolated_and_inactive(self) -> None:
        value = self.manifest
        self.assertEqual(value["contract"], "rozkalns-weather.public-runtime-helper-install.v1")
        self.assertEqual(value["status"], "SOURCE_ONLY_INSTALL_DISABLED")
        self.assertEqual(value["install_root"], DEDICATED_ROOT)
        self.assertEqual(value["executable_path"], EXECUTABLE)
        self.assertEqual(value["package_root"], PACKAGE_ROOT)
        self.assertEqual(value["required_owner_uid"], 0)
        self.assertEqual(value["required_owner_gid"], 0)
        self.assertEqual(value["artifact_count"], 13)
        self.assertEqual(len(self.artifacts), 13)

        destinations = [item["destination"] for item in self.artifacts]
        self.assertEqual(len(destinations), len(set(destinations)))
        self.assertIn(EXECUTABLE, destinations)
        for item in self.artifacts:
            source = ROOT / item["source"]
            self.assertTrue(source.is_file(), item["source"])
            destination = item["destination"]
            self.assertTrue(destination == EXECUTABLE or destination.startswith(PACKAGE_ROOT + "/"))
            self.assertFalse(destination.startswith(EXISTING_EXECUTOR_ROOT + "/"))
            self.assertIn(item["mode"], {"0755", "0644"})

        closure = value["closure_policy"]
        self.assertTrue(closure["exact_list_only"])
        for key in (
            "wildcard_copy",
            "ambient_repository_checkout_required",
            "pythonpath_required",
            "user_site_packages_required",
            "existing_deploy_executor_package_mutation",
            "unrelated_transport_state_credential_modules_installed",
            "package_initializer_imports_other_modules",
        ):
            self.assertFalse(closure[key])
        for enabled in value["activation"].values():
            self.assertFalse(enabled)

    def test_manifest_contains_only_the_transitive_weather_import_closure(self) -> None:
        module_artifacts = {
            Path(item["destination"]).stem: item
            for item in self.artifacts
            if item["kind"] == "module"
        }
        self.assertEqual(set(module_artifacts), EXPECTED_MODULES)

        for module_name, item in module_artifacts.items():
            tree = ast.parse((ROOT / item["source"]).read_text(encoding="utf-8"), filename=item["source"])
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level:
                    self.assertEqual(node.level, 1, f"unexpected relative import depth in {module_name}")
                    self.assertIsNotNone(node.module, f"implicit relative import in {module_name}")
                    dependency = node.module.split(".", 1)[0]
                    self.assertIn(
                        dependency,
                        EXPECTED_MODULES,
                        f"{module_name} imports uninstalled relative module {dependency}",
                    )

        entry_tree = ast.parse(ENTRYPOINT_SOURCE.read_text(encoding="utf-8"), filename=str(ENTRYPOINT_SOURCE))
        entry_modules = set()
        for node in ast.walk(entry_tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith("deploy_executor."):
                entry_modules.add(node.module.split(".", 1)[1].split(".", 1)[0])
        self.assertTrue(entry_modules)
        self.assertTrue(entry_modules <= EXPECTED_MODULES)

    def test_package_initializer_is_import_free(self) -> None:
        item = next(item for item in self.artifacts if item["kind"] == "package_init")
        tree = ast.parse((ROOT / item["source"]).read_text(encoding="utf-8"), filename=item["source"])
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertEqual(imports, [])

    def test_clean_environment_loads_isolated_package_then_fails_at_activation_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            host_root = Path(tmp) / "host-root"
            for item in self.artifacts:
                destination = host_root / item["destination"].lstrip("/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / item["source"], destination)
                destination.chmod(int(item["mode"], 8))

            executable = host_root / EXECUTABLE.lstrip("/")
            support_root = host_root / DEDICATED_ROOT.lstrip("/")
            package_init = support_root / "deploy_executor/__init__.py"
            self.assertTrue(executable.is_file())
            self.assertTrue(package_init.is_file())

            env = {
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "HOME": "/nonexistent",
                "PYTHONNOUSERSITE": "1",
            }
            result = subprocess.run(
                [sys.executable, "-I", str(executable)],
                cwd=host_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 78, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("WEATHER_STAGE_HELPER=STOP error=WeatherStageHelperError", result.stderr)
            self.assertNotIn("WeatherHelperInstallLayoutError", result.stderr)
            self.assertNotIn("ModuleNotFoundError", result.stderr)
            self.assertNotIn("ImportError", result.stderr)

    def test_entrypoint_does_not_accept_ambient_python_path(self) -> None:
        source = ENTRYPOINT_SOURCE.read_text(encoding="utf-8")
        self.assertIn('_SUPPORT_DIR_NAME = "rozkalns-weather-public-runtime"', source)
        self.assertIn("sys.path.insert(0, str(_SUPPORT_ROOT))", source)
        self.assertIn("Path(deploy_executor.__file__", source)
        for forbidden in ("PYTHONPATH", "site-packages", "ops/lib", "os.environ", "sys.path.append"):
            self.assertNotIn(forbidden, source)

    def test_existing_weather_execution_invariants_remain_green(self) -> None:
        result = subprocess.run(
            [sys.executable, str(EXECUTION_TEST)],
            cwd=ROOT,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PYTHONNOUSERSITE": "1",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
