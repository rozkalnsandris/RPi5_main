#!/usr/bin/env python3
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ADAPTER = ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-refresh-runtime"


def load(path: Path, name: str):
    loader = SourceFileLoader(name, str(path))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def _dataclass_payload() -> bytes:
    return b'''from dataclasses import dataclass

class WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(RuntimeError):
    pass

@dataclass(frozen=True)
class RuntimeMarker:
    issue_number: int

class ConcreteBoundaryRefreshRevalidator:
    def __init__(self):
        self.calls = 0

    def revalidate(self, issue_number):
        self.calls += 1
        return (issue_number, self.calls)


def _stable(first, final):
    return None


def execute_prevalidated_refresh(preconsume):
    marker = RuntimeMarker(preconsume[0])
    return {"status": "PASS", "issue": marker.issue_number}


def run_privileged_installer_boundary_refresh(issue_number):
    revalidator = ConcreteBoundaryRefreshRevalidator()
    first = revalidator.revalidate(issue_number)
    final = revalidator.revalidate(issue_number)
    _stable(first, final)
    preconsume = revalidator.revalidate(issue_number)
    _stable(final, preconsume)
    return execute_prevalidated_refresh(preconsume)
'''


def _failing_dataclass_payload() -> bytes:
    return b'''from dataclasses import dataclass

@dataclass(frozen=True)
class RuntimeMarker:
    value: int

raise RuntimeError("secret-runtime-loader-detail")
'''


def _prepare_trusted_dependency_surface(adapter):
    td = tempfile.TemporaryDirectory()
    trusted = Path(td.name) / "trusted"
    package = trusted / "ops/lib/deploy_executor"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    for path in (trusted, trusted / "ops", trusted / "ops/lib", package):
        path.chmod(0o755)

    adapter.ROOT_UID = os.getuid()
    adapter.ROOT_GID = os.getgid()
    adapter.TRUSTED_CHECKOUT = trusted
    adapter.TRUSTED_LIB = trusted / "ops/lib"

    previous_package = sys.modules.pop("deploy_executor", None)
    return td, previous_package


def _cleanup_trusted_dependency_surface(td, previous_package):
    sys.modules.pop("deploy_executor", None)
    if previous_package is not None:
        sys.modules["deploy_executor"] = previous_package
    td.cleanup()


def test_dataclass_runtime_loads_with_temporary_module_registration():
    adapter = load(RUNTIME_ADAPTER, "boundary_runtime_adapter_dataclass")
    td, previous_package = _prepare_trusted_dependency_surface(adapter)
    module_name = adapter.VERIFIED_RUNTIME_MODULE_NAME
    missing = object()
    previous_runtime = sys.modules.pop(module_name, missing)
    try:
        entry = adapter._load_verified_runtime(_dataclass_payload())
        assert module_name not in sys.modules
        assert entry(731) == {"status": "PASS", "issue": 731}
    finally:
        if previous_runtime is not missing:
            sys.modules[module_name] = previous_runtime
        _cleanup_trusted_dependency_surface(td, previous_package)


def test_verified_runtime_restores_preexisting_module_identity():
    adapter = load(RUNTIME_ADAPTER, "boundary_runtime_adapter_restore")
    td, previous_package = _prepare_trusted_dependency_surface(adapter)
    module_name = adapter.VERIFIED_RUNTIME_MODULE_NAME
    missing = object()
    previous_runtime = sys.modules.get(module_name, missing)
    marker = ModuleType(module_name)
    sys.modules[module_name] = marker
    try:
        entry = adapter._load_verified_runtime(_dataclass_payload())
        assert sys.modules[module_name] is marker
        assert entry(731) == {"status": "PASS", "issue": 731}
    finally:
        if previous_runtime is missing:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_runtime
        _cleanup_trusted_dependency_surface(td, previous_package)


def test_runtime_setup_failure_is_sanitized_and_restores_module():
    adapter = load(RUNTIME_ADAPTER, "boundary_runtime_adapter_setup_failure")
    td, previous_package = _prepare_trusted_dependency_surface(adapter)
    module_name = adapter.VERIFIED_RUNTIME_MODULE_NAME
    missing = object()
    previous_runtime = sys.modules.get(module_name, missing)
    marker = ModuleType(module_name)
    sys.modules[module_name] = marker

    adapter.ROOT_UID = os.geteuid()
    manager_snapshot = ("a" * 40, "0" * 64)
    adapter._manager_checkout = lambda **kwargs: (Path(td.name) / "manager", os.getuid(), os.getgid(), Path(td.name))
    adapter._verified_runtime_bytes = lambda *args, **kwargs: (manager_snapshot, _failing_dataclass_payload())

    try:
        try:
            adapter.run_from_bootstrap(731)
        except adapter.BootstrapRuntimeAdapterError as exc:
            assert str(exc) == "WeatherNext private installer-boundary refresh failed closed"
            assert getattr(exc, "failure_stage", None) == "runtime_setup"
            assert getattr(exc, "error_code", None) == "PRECONSUME_RUNTIME_SETUP_FAILED"
            assert "secret-runtime-loader-detail" not in str(exc)
            assert sys.modules[module_name] is marker
        else:
            raise AssertionError("verified runtime setup failure must fail closed")
    finally:
        if previous_runtime is missing:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_runtime
        _cleanup_trusted_dependency_surface(td, previous_package)


if __name__ == "__main__":
    test_dataclass_runtime_loads_with_temporary_module_registration()
    test_verified_runtime_restores_preexisting_module_identity()
    test_runtime_setup_failure_is_sanitized_and_restores_module()
    print("WeatherNext verified runtime module-registration tests: PASS")
