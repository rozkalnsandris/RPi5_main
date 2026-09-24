#!/usr/bin/env python3
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BROKER = ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap"
CONTRACT = ROOT / "ops/contracts/weathernext-private-installer-boundary-bootstrap-v1.json"
FIXTURE = ROOT / "tests/fixtures/weathernext-installer-boundary-bootstrap-v1.json"


def load_broker():
    loader = SourceFileLoader("weathernext_installer_boundary_bootstrap", str(BROKER))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def result(argv, stdout="", stderr="", returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_contract_and_frozen_anchors():
    module = load_broker()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert contract["schema"] == "rpi5.weathernext-private-installer-boundary-bootstrap.v1"
    assert contract["implementation_issue"] == 723
    assert contract["source_repository"] == "rozkalnsandris/RPi5_main"
    assert contract["source_entrypoint"] == "ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap"
    assert contract["installed_entrypoint"] == "/usr/local/sbin/rpi5-weathernext-private-installer-boundary-bootstrap"
    assert contract["future_refresh_runtime"] == module.RUNTIME_RELATIVE.as_posix()
    assert contract["bootstrap_interface"] == module.BOOTSTRAP_INTERFACE
    assert contract["caller_authority"] == ["authorization_issue_number"]
    assert contract["runtime_live_authority"] is False
    assert contract["source_merge_authorizes_live"] is False
    assert contract["refresh_operation_executed_by_bootstrap_install"] is False
    assert contract["mutation_budget"] == [
        {
            "category": "filesystem.weathernext-private-installer-boundary-bootstrap-install",
            "max_operations": 1,
        }
    ]
    assert contract["separate_from_refresh_mutation_budget"] is True
    assert contract["rollback_policy"] == "NONE"
    assert contract["automatic_retry"] is False
    assert contract["automatic_cleanup"] is False
    assert contract["automatic_rollback"] is False

    assert fixture["known_stale_head"] == module.KNOWN_STALE_HEAD
    assert fixture["known_entrypoint_blob"] == module.KNOWN_ENTRYPOINT_BLOB
    assert fixture["known_stale_dispatch_blob"] == module.KNOWN_STALE_DISPATCH_BLOB
    assert fixture["stale_dispatch_knows_refresh_operation"] is False
    assert fixture["bootstrap_entrypoint_is_distinct_from_stale_entrypoint"] is True


def test_git_blob_hash_and_runtime_interface():
    module = load_broker()
    data = (
        b'BOOTSTRAP_INTERFACE = "'
        + module.BOOTSTRAP_INTERFACE.encode("ascii")
        + b'"\n'
        + b"def run_from_bootstrap(issue_number):\n"
        + b'    return {"result": "PASS", "issue": issue_number}\n'
    )
    assert len(module._git_blob_sha1(data)) == 40
    entry = module._load_runtime(data)
    assert entry(723) == {"result": "PASS", "issue": 723}

    try:
        module._load_runtime(b'BOOTSTRAP_INTERFACE = "wrong"\ndef run_from_bootstrap(n): return {}\n')
    except module.BootstrapReachabilityError as exc:
        assert "interface mismatch" in str(exc)
    else:
        raise AssertionError("wrong bootstrap interface must fail closed")


def test_end_to_end_reachability_from_known_stale_boundary():
    module = load_broker()
    uid = os.getuid()
    gid = os.getgid()
    source_sha = "a" * 40

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        trusted = root / "trusted"
        manager_home = root / "home"
        manager = manager_home / "RPi5_main"
        installed = root / "installed-entrypoint"
        dispatch = trusted / module.STALE_DISPATCH_RELATIVE
        runtime = manager / module.RUNTIME_RELATIVE

        dispatch.parent.mkdir(parents=True)
        runtime.parent.mkdir(parents=True)
        manager_home.mkdir(exist_ok=True)

        trusted.chmod(0o755)
        manager.chmod(0o755)

        installed_bytes = b"known stale entrypoint\n"
        stale_dispatch_bytes = b"known stale dispatch without refresh route\n"
        runtime_bytes = (
            b'BOOTSTRAP_INTERFACE = "'
            + module.BOOTSTRAP_INTERFACE.encode("ascii")
            + b'"\n'
            + b"def run_from_bootstrap(issue_number):\n"
            + b'    return {"result": "PASS", "issue": issue_number, "transport": "bootstrap"}\n'
        )

        installed.write_bytes(installed_bytes)
        installed.chmod(0o755)
        dispatch.write_bytes(stale_dispatch_bytes)
        dispatch.chmod(0o644)
        runtime.write_bytes(runtime_bytes)
        runtime.chmod(0o755)

        module.ROOT_UID = uid
        module.ROOT_GID = gid
        module.TRUSTED_CHECKOUT = trusted
        module.INSTALLED_ENTRYPOINT = installed
        module.KNOWN_STALE_HEAD = "7" * 40
        module.KNOWN_ENTRYPOINT_BLOB = module._git_blob_sha1(installed_bytes)
        module.KNOWN_STALE_DISPATCH_BLOB = module._git_blob_sha1(stale_dispatch_bytes)
        module.REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
        original_geteuid = module.os.geteuid
        module.os.geteuid = lambda: uid

        runtime_blob = module._git_blob_sha1(runtime_bytes)

        def fake_runner(argv, **kwargs):
            argv = tuple(argv)
            if argv[:2] == ("/usr/bin/git", "ls-remote"):
                return result(argv, f"{source_sha}\trefs/heads/main\n")
            try:
                git_index = argv.index("/usr/bin/git")
            except ValueError as exc:
                raise AssertionError(f"missing fixed git executable: {argv}") from exc
            git_argv = argv[git_index:]
            assert git_argv[:2] == ("/usr/bin/git", "--no-optional-locks")
            assert git_argv[2] == "-C"
            repo = Path(git_argv[3])
            args = git_argv[4:]
            if repo == trusted:
                assert argv[0] == "/usr/bin/git"
                if args == ("rev-parse", "HEAD"):
                    return result(argv, module.KNOWN_STALE_HEAD + "\n")
                if args == ("status", "--porcelain", "--untracked-files=all"):
                    return result(argv, "")
                if args == ("remote", "get-url", "origin"):
                    return result(argv, module.REVIEWED_ORIGIN + "\n")
            if repo == manager:
                assert argv[:4] == (
                    "/usr/sbin/runuser",
                    "-u",
                    module.MANAGER_USERNAME,
                    "--",
                )
                if args == ("rev-parse", "HEAD"):
                    return result(argv, source_sha + "\n")
                if args == ("status", "--porcelain", "--untracked-files=all"):
                    return result(argv, "")
                if args == ("remote", "get-url", "origin"):
                    return result(argv, module.REVIEWED_ORIGIN + "\n")
                if args == ("ls-tree", source_sha, "--", module.RUNTIME_RELATIVE.as_posix()):
                    return result(
                        argv,
                        f"100755 blob {runtime_blob}\t{module.RUNTIME_RELATIVE.as_posix()}\n",
                    )
            raise AssertionError(f"unexpected git call: {argv}")

        account = SimpleNamespace(pw_uid=uid, pw_gid=gid, pw_dir=str(manager_home))
        try:
            receipt = module.execute(
                123,
                runner=fake_runner,
                pwd_lookup=lambda name: account if name == module.MANAGER_USERNAME else None,
            )
        finally:
            module.os.geteuid = original_geteuid

        assert receipt == {"result": "PASS", "issue": 123, "transport": "bootstrap"}


def test_broker_is_identity_only_and_independent_of_stale_dispatch():
    source = BROKER.read_text(encoding="utf-8")
    assert 'parser.add_argument("--issue-number"' in source
    assert "from deploy_executor.weather_private_privileged_dispatch" not in source
    assert "import deploy_executor.weather_private_privileged_dispatch" not in source
    assert "shell=False" in source
    assert "/usr/sbin/runuser" in source
    assert "git fetch" not in source
    assert "git reset" not in source
    assert "git clean" not in source
    assert "git pull" not in source
    assert "git merge" not in source
    assert "git rebase" not in source
    assert "os.system" not in source
    assert "subprocess.Popen" not in source


if __name__ == "__main__":
    test_contract_and_frozen_anchors()
    test_git_blob_hash_and_runtime_interface()
    test_end_to_end_reachability_from_known_stale_boundary()
    test_broker_is_identity_only_and_independent_of_stale_dispatch()
    print("WeatherNext installer-boundary bootstrap tests: PASS")
