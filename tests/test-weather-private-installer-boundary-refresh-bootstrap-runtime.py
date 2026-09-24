#!/usr/bin/env python3
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap"
RUNTIME_ADAPTER = ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-refresh-runtime"
CONTRACT = ROOT / "ops/deploy/weather-private-installer-boundary-refresh.json"


def load(path: Path, name: str):
    loader = SourceFileLoader(name, str(path))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_bootstrap_loads_exact_runtime_interface():
    bootstrap = load(BOOTSTRAP, "boundary_bootstrap")
    data = RUNTIME_ADAPTER.read_bytes()
    entry = bootstrap._load_runtime(data)
    assert callable(entry)

    source = data.decode("utf-8")
    assert f'BOOTSTRAP_INTERFACE = "{bootstrap.BOOTSTRAP_INTERFACE}"' in source
    assert 'RUNTIME_MODULE_RELATIVE = Path("ops/lib/deploy_executor/weather_private_installer_boundary_refresh_runtime.py")' in source
    assert 'TRUSTED_CHECKOUT = Path("/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted")' in source
    assert 'MANAGER_USERNAME = "andris"' in source
    assert "direct execution is forbidden; use the installed bootstrap launcher" in source
    assert "shell=False" in source
    assert "/usr/sbin/runuser" in source
    assert "os.system" not in source
    assert "subprocess.Popen" not in source
    for forbidden in ('"fetch"', '"clone"', '"reset"', '"clean"', '"pull"', '"merge"', '"rebase"', '"switch"'):
        assert forbidden not in source


def test_adapter_verifies_manager_runtime_blob_without_mutation():
    adapter = load(RUNTIME_ADAPTER, "boundary_runtime_adapter")
    uid = os.getuid()
    gid = os.getgid()
    head = "a" * 40

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        manager = home / adapter.MANAGER_REPO_BASENAME
        runtime_path = manager / adapter.RUNTIME_MODULE_RELATIVE
        runtime_path.parent.mkdir(parents=True)
        payload = b"def run_privileged_installer_boundary_refresh(issue_number):\n    return {'issue': issue_number}\n"
        runtime_path.write_bytes(payload)
        runtime_path.chmod(0o644)
        blob = adapter._git_blob_sha1(payload)

        def fake_runner(argv, **kwargs):
            argv = tuple(argv)
            git_index = argv.index("/usr/bin/git")
            git_argv = argv[git_index:]
            assert git_argv[:2] == ("/usr/bin/git", "--no-optional-locks")
            assert git_argv[2] == "-C"
            assert Path(git_argv[3]) == manager
            args = git_argv[4:]
            if args == ("rev-parse", "HEAD"):
                return result(head + "\n")
            if args == ("status", "--porcelain", "--untracked-files=all"):
                return result("")
            if args == ("remote", "get-url", "origin"):
                return result(adapter.REVIEWED_ORIGIN + "\n")
            if args == ("ls-tree", head, "--", adapter.RUNTIME_MODULE_RELATIVE.as_posix()):
                return result(f"100644 blob {blob}\t{adapter.RUNTIME_MODULE_RELATIVE.as_posix()}\n")
            raise AssertionError(f"unexpected Git argv: {args}")

        snapshot, observed = adapter._verified_runtime_bytes(
            manager,
            uid,
            gid,
            home,
            runner=fake_runner,
        )
        assert snapshot[0] == head
        assert observed == payload


def test_adapter_loads_verified_module_against_root_owned_dependency_surface():
    adapter = load(RUNTIME_ADAPTER, "boundary_runtime_adapter_loader")
    uid = os.getuid()
    gid = os.getgid()

    with tempfile.TemporaryDirectory() as td:
        trusted = Path(td) / "trusted"
        package = trusted / "ops/lib/deploy_executor"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        for path in (trusted, trusted / "ops", trusted / "ops/lib", package):
            path.chmod(0o755)

        adapter.ROOT_UID = uid
        adapter.ROOT_GID = gid
        adapter.TRUSTED_CHECKOUT = trusted
        adapter.TRUSTED_LIB = trusted / "ops/lib"

        previous = sys.modules.pop("deploy_executor", None)
        try:
            payload = (
                b"def run_privileged_installer_boundary_refresh(issue_number):\n"
                b"    return {'status': 'PASS', 'issue': issue_number}\n"
            )
            entry = adapter._load_verified_runtime(payload)
            assert entry(721) == {"status": "PASS", "issue": 721}
        finally:
            sys.modules.pop("deploy_executor", None)
            if previous is not None:
                sys.modules["deploy_executor"] = previous


def test_contract_binds_bootstrap_and_refresh_runtime_without_live_authority():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["implementation_issue"] == 700
    assert contract["transport_implementation_issue"] == 721
    assert contract["bootstrap_prerequisite_issue"] == 723
    assert contract["bootstrap_runtime"] == "ops/bin/rpi5-weathernext-private-installer-boundary-refresh-runtime"
    assert contract["bootstrap_interface"] == "rozkalns.weathernext-private-installer-boundary-refresh-bootstrap-callable.v1"
    assert contract["runtime_module"] == "ops/lib/deploy_executor/weather_private_installer_boundary_refresh_runtime.py"
    assert contract["caller_authority"] == ["authorization_issue_number"]
    assert contract["source_merge_authorizes_live"] is False
    assert contract["mutation_budget"] == [
        {"category": "git.weathernext-private-installer-checkout-fetch", "max_operations": 1},
        {"category": "git.weathernext-private-installer-trusted-checkout-advance", "max_operations": 1},
        {"category": "filesystem.weathernext-private-installer-entrypoint-replace", "max_operations": 1},
    ]
    assert contract["rollback_policy"] == "NONE"
    assert contract["automatic_retry"] is False
    assert contract["automatic_cleanup"] is False
    assert contract["automatic_rollback"] is False


if __name__ == "__main__":
    test_bootstrap_loads_exact_runtime_interface()
    test_adapter_verifies_manager_runtime_blob_without_mutation()
    test_adapter_loads_verified_module_against_root_owned_dependency_surface()
    test_contract_binds_bootstrap_and_refresh_runtime_without_live_authority()
    print("WeatherNext installer-boundary refresh bootstrap runtime tests: PASS")
