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


def _runtime_payload(*, fail_stage: str | None = None) -> bytes:
    return f'''class WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(RuntimeError):
    pass

class ConcreteBoundaryRefreshRevalidator:
    def __init__(self):
        self.calls = 0
        self.accepted = object()
        self.prepared = object()

    def revalidate(self, issue_number):
        self.calls += 1
        if {fail_stage!r} == "revalidate_first" and self.calls == 1:
            raise RuntimeError("secret-token-first")
        if {fail_stage!r} == "revalidate_final" and self.calls == 2:
            raise RuntimeError("secret-token-final")
        if {fail_stage!r} == "revalidate_preconsume" and self.calls == 3:
            raise RuntimeError("secret-token-preconsume")
        return (issue_number, self.calls)

_stable_calls = 0

def _stable(first, final):
    global _stable_calls
    _stable_calls += 1
    if {fail_stage!r} == "stability_first_final" and _stable_calls == 1:
        raise RuntimeError("secret-path-stability-one")
    if {fail_stage!r} == "stability_final_preconsume" and _stable_calls == 2:
        raise RuntimeError("secret-path-stability-two")


def execute_prevalidated_refresh(*args, **kwargs):
    if {fail_stage!r} == "postconsume":
        raise RuntimeError("postconsume-secret-must-not-be-preconsume")
    return {{"status": "PASS", "issue": args[0][0]}}


def run_privileged_installer_boundary_refresh(issue_number):
    revalidator = ConcreteBoundaryRefreshRevalidator()
    first = revalidator.revalidate(issue_number)
    final = revalidator.revalidate(issue_number)
    _stable(first, final)
    preconsume = revalidator.revalidate(issue_number)
    _stable(final, preconsume)
    if {fail_stage!r} == "preconsume_finalize":
        raise RuntimeError("secret-finalize")
    return execute_prevalidated_refresh(preconsume)
'''.encode("utf-8")


def _load_adapter_entry(adapter, payload: bytes):
    uid = os.getuid()
    gid = os.getgid()
    td = tempfile.TemporaryDirectory()
    trusted = Path(td.name) / "trusted"
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
        entry = adapter._load_verified_runtime(payload)
    except Exception:
        td.cleanup()
        if previous is not None:
            sys.modules["deploy_executor"] = previous
        raise
    return td, previous, entry


def _cleanup_adapter_entry(td, previous):
    sys.modules.pop("deploy_executor", None)
    if previous is not None:
        sys.modules["deploy_executor"] = previous
    td.cleanup()


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
        payload = _runtime_payload()
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
    td, previous, entry = _load_adapter_entry(adapter, _runtime_payload())
    try:
        assert entry(721) == {"status": "PASS", "issue": 721}
    finally:
        _cleanup_adapter_entry(td, previous)


def test_adapter_sanitizes_fixed_preconsume_stage_codes():
    expected = {
        "revalidate_first": "PRECONSUME_REVALIDATE_FIRST_FAILED",
        "revalidate_final": "PRECONSUME_REVALIDATE_FINAL_FAILED",
        "stability_first_final": "PRECONSUME_STABILITY_FIRST_FINAL_FAILED",
        "revalidate_preconsume": "PRECONSUME_REVALIDATE_PRECONSUME_FAILED",
        "stability_final_preconsume": "PRECONSUME_STABILITY_FINAL_PRECONSUME_FAILED",
        "preconsume_finalize": "PRECONSUME_FINALIZE_FAILED",
    }
    for stage, code in expected.items():
        adapter = load(RUNTIME_ADAPTER, f"boundary_runtime_adapter_{stage}")
        td, previous, entry = _load_adapter_entry(adapter, _runtime_payload(fail_stage=stage))
        try:
            try:
                entry(721)
            except Exception as exc:
                assert getattr(exc, "failure_stage", None) == stage
                assert getattr(exc, "error_code", None) == code
                assert str(exc) == "WeatherNext private installer-boundary refresh failed closed"
                assert "secret" not in str(exc)
            else:
                raise AssertionError(f"{stage} must fail closed")
        finally:
            _cleanup_adapter_entry(td, previous)


def test_adapter_sanitizes_replay_consume_boundary_before_backend_apply():
    adapter = load(RUNTIME_ADAPTER, "boundary_runtime_adapter_replay_consume")
    backend_calls: list[object] = []

    class RuntimeErrorType(RuntimeError):
        pass

    class Revalidator:
        def revalidate(self, issue_number):
            return issue_number

    def stable(first, final):
        return None

    class Replay:
        def consume(self, request_id):
            raise RuntimeError("secret-durable-consume-detail")

        def mark_succeeded(self, request_id):
            raise AssertionError("mark_succeeded must not run")

    class Backend:
        def apply(self, prepared):
            backend_calls.append(prepared)
            return {"status": "PASS", "authorization_consumed": True}

    replay = Replay()
    backend = Backend()

    def execute_prevalidated_refresh(evidence, *, prepared, accepted, replay, backend):
        replay.consume("request-1")
        receipt = dict(backend.apply(prepared))
        replay.mark_succeeded("request-1")
        receipt["authorization_consumed"] = True
        return receipt

    def run_privileged_installer_boundary_refresh(issue_number):
        revalidator = Revalidator()
        first = revalidator.revalidate(issue_number)
        final = revalidator.revalidate(issue_number)
        stable(first, final)
        preconsume = revalidator.revalidate(issue_number)
        stable(final, preconsume)
        return execute_prevalidated_refresh(
            preconsume,
            prepared=object(),
            accepted=object(),
            replay=replay,
            backend=backend,
        )

    namespace = {
        "run_privileged_installer_boundary_refresh": run_privileged_installer_boundary_refresh,
        "WeatherNextPrivateInstallerBoundaryRefreshRuntimeError": RuntimeErrorType,
        "ConcreteBoundaryRefreshRevalidator": Revalidator,
        "_stable": stable,
        "execute_prevalidated_refresh": execute_prevalidated_refresh,
    }
    entry = adapter._instrumented_runtime_entry(namespace)
    try:
        entry(721)
    except Exception as exc:
        assert getattr(exc, "failure_stage", None) == "replay_consume"
        assert getattr(exc, "error_code", None) == "PRECONSUME_REPLAY_CONSUME_FAILED"
        assert str(exc) == "WeatherNext private installer-boundary refresh failed closed"
        assert "secret" not in str(exc)
    else:
        raise AssertionError("replay consume failure must fail closed")
    assert backend_calls == []


def test_bootstrap_preserves_replay_consume_stage_without_consumed_claim():
    bootstrap = load(BOOTSTRAP, "boundary_bootstrap_replay_consume")
    runtime_error = RuntimeError("secret-durable-consume-detail")
    setattr(runtime_error, "failure_stage", "replay_consume")
    setattr(runtime_error, "error_code", "PRECONSUME_REPLAY_CONSUME_FAILED")
    converted = bootstrap._runtime_failure(runtime_error)
    receipt = bootstrap._failure_receipt(converted)
    assert receipt["result"] == "STOP"
    assert receipt["failure_stage"] == "replay_consume"
    assert receipt["error_code"] == "PRECONSUME_REPLAY_CONSUME_FAILED"
    assert receipt["automatic_retry"] is False
    assert receipt["automatic_cleanup"] is False
    assert receipt["automatic_rollback"] is False
    assert "authorization_consumed" not in receipt
    assert "mutation_categories" not in receipt
    assert "secret" not in json.dumps(receipt, sort_keys=True)


def test_adapter_never_labels_postconsume_failure_as_preconsume():
    adapter = load(RUNTIME_ADAPTER, "boundary_runtime_adapter_postconsume")
    td, previous, entry = _load_adapter_entry(adapter, _runtime_payload(fail_stage="postconsume"))
    try:
        try:
            entry(721)
        except Exception as exc:
            assert getattr(exc, "failure_stage", None) is None
            assert getattr(exc, "error_code", None) is None
        else:
            raise AssertionError("post-consume failure must propagate")
    finally:
        _cleanup_adapter_entry(td, previous)


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
    test_adapter_sanitizes_fixed_preconsume_stage_codes()
    test_adapter_sanitizes_replay_consume_boundary_before_backend_apply()
    test_bootstrap_preserves_replay_consume_stage_without_consumed_claim()
    test_adapter_never_labels_postconsume_failure_as_preconsume()
    test_contract_binds_bootstrap_and_refresh_runtime_without_live_authority()
    print("WeatherNext installer-boundary refresh bootstrap runtime tests: PASS")