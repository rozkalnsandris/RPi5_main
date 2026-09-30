#!/usr/bin/env python3
from __future__ import annotations

import base64
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


class FakeGitHub:
    def __init__(self, payloads):
        self.payloads = payloads
        self.paths = []

    def get_json(self, path):
        self.paths.append(path)
        try:
            return self.payloads[path]
        except KeyError as exc:
            raise AssertionError(f"unexpected public GitHub path: {path}") from exc


def public_payloads(
    module,
    *,
    source_sha,
    adapter_bytes,
    runtime_module_bytes,
    adapter_mode="100755",
    runtime_module_mode="100644",
    adapter_tree_blob=None,
    runtime_module_tree_blob=None,
    adapter_content_bytes=None,
    runtime_module_content_bytes=None,
    tree_truncated=False,
):
    tree_sha = "c" * 40
    adapter_path = module.RUNTIME_RELATIVE.as_posix()
    runtime_module_path = module.RUNTIME_MODULE_RELATIVE.as_posix()
    adapter_blob = (
        adapter_tree_blob
        if adapter_tree_blob is not None
        else module._git_blob_sha1(adapter_bytes)
    )
    runtime_module_blob = (
        runtime_module_tree_blob
        if runtime_module_tree_blob is not None
        else module._git_blob_sha1(runtime_module_bytes)
    )
    adapter_content = adapter_bytes if adapter_content_bytes is None else adapter_content_bytes
    runtime_module_content = (
        runtime_module_bytes
        if runtime_module_content_bytes is None
        else runtime_module_content_bytes
    )
    return {
        f"/repos/{module.SOURCE_REPOSITORY}/branches/main": {
            "commit": {"sha": source_sha}
        },
        f"/repos/{module.SOURCE_REPOSITORY}/git/commits/{source_sha}": {
            "sha": source_sha,
            "tree": {"sha": tree_sha},
        },
        f"/repos/{module.SOURCE_REPOSITORY}/git/trees/{tree_sha}?recursive=1": {
            "truncated": tree_truncated,
            "tree": [
                {
                    "path": adapter_path,
                    "mode": adapter_mode,
                    "type": "blob",
                    "sha": adapter_blob,
                },
                {
                    "path": runtime_module_path,
                    "mode": runtime_module_mode,
                    "type": "blob",
                    "sha": runtime_module_blob,
                },
            ],
        },
        f"/repos/{module.SOURCE_REPOSITORY}/contents/{adapter_path}?ref={source_sha}": {
            "type": "file",
            "path": adapter_path,
            "sha": adapter_blob,
            "encoding": "base64",
            "content": base64.b64encode(adapter_content).decode("ascii"),
        },
        f"/repos/{module.SOURCE_REPOSITORY}/contents/{runtime_module_path}?ref={source_sha}": {
            "type": "file",
            "path": runtime_module_path,
            "sha": runtime_module_blob,
            "encoding": "base64",
            "content": base64.b64encode(runtime_module_content).decode("ascii"),
        },
    }


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

    runtime_source = contract["bootstrap_runtime_source"]
    assert "requires_manager_head_equal_remote_main" not in runtime_source
    assert runtime_source["manager_head_may_lag_when_runtime_pair_exact_current"] is True
    assert runtime_source["exact_current_source_repository"] == module.SOURCE_REPOSITORY
    assert runtime_source["exact_current_source_ref"] == "main"
    assert runtime_source["exact_current_public_reads_credential_free"] is True
    assert runtime_source["exact_current_commit_tree_must_match"] is True
    assert runtime_source["exact_current_runtime_paths"] == [
        module.RUNTIME_RELATIVE.as_posix(),
        module.RUNTIME_MODULE_RELATIVE.as_posix(),
    ]
    assert runtime_source["exact_current_runtime_git_modes"] == {
        module.RUNTIME_RELATIVE.as_posix(): "100755",
        module.RUNTIME_MODULE_RELATIVE.as_posix(): "100644",
    }
    assert runtime_source["exact_current_runtime_git_blob_and_contents_must_match"] is True
    assert runtime_source["manager_runtime_pair_git_blobs_must_equal_exact_current"] is True
    assert runtime_source["manager_runtime_pair_worktree_bytes_must_equal_exact_current"] is True
    assert runtime_source["runtime_adapter_filesystem_mode_uses_safe_policy"] is True
    assert runtime_source["runtime_module_filesystem_mode"] == "0644"
    assert runtime_source["manager_head_index_worktree_must_remain_unchanged"] is True
    assert runtime_source["manager_checkout_mutation_allowed"] is False

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


def test_failure_receipt_exposes_only_allowlisted_preconsume_telemetry():
    module = load_broker()
    stage = "revalidate_first"
    code = module.PRECONSUME_FAILURE_TELEMETRY[stage]
    underlying = RuntimeError("secret-token /private/path should-never-appear")
    underlying.failure_stage = stage
    underlying.error_code = code

    sanitized = module._runtime_failure(underlying)
    receipt = module._failure_receipt(sanitized)
    encoded = json.dumps(receipt, sort_keys=True)
    assert receipt["failure_stage"] == stage
    assert receipt["error_code"] == code
    assert receipt["reason"] == "verified refresh runtime failed closed"
    assert receipt["automatic_retry"] is False
    assert receipt["automatic_cleanup"] is False
    assert receipt["automatic_rollback"] is False
    assert "secret-token" not in encoded
    assert "/private/path" not in encoded

    mismatched = module.BootstrapReachabilityError(
        "another secret",
        failure_stage=stage,
        error_code="NOT_ALLOWLISTED",
    )
    generic = module._failure_receipt(mismatched)
    assert "failure_stage" not in generic
    assert "error_code" not in generic
    assert generic["reason"] == "verified installer-boundary bootstrap failed closed"
    assert "another secret" not in json.dumps(generic, sort_keys=True)

    plain = module._failure_receipt(module.BootstrapReachabilityError("raw internal path"))
    assert "failure_stage" not in plain
    assert "error_code" not in plain
    assert "raw internal path" not in json.dumps(plain, sort_keys=True)


def test_public_exact_current_pair_verifies_commit_tree_modes_blobs_and_contents():
    module = load_broker()
    source_sha = "a" * 40
    adapter_bytes = b"#!/usr/bin/env python3\n# adapter\n"
    runtime_module_bytes = b"# runtime module\n"
    client = FakeGitHub(
        public_payloads(
            module,
            source_sha=source_sha,
            adapter_bytes=adapter_bytes,
            runtime_module_bytes=runtime_module_bytes,
        )
    )

    actual_sha, proof = module._exact_current_runtime_pair(client)
    assert actual_sha == source_sha
    assert proof[module.RUNTIME_RELATIVE.as_posix()][0] == "100755"
    assert proof[module.RUNTIME_MODULE_RELATIVE.as_posix()][0] == "100644"
    assert proof[module.RUNTIME_RELATIVE.as_posix()][2] == adapter_bytes
    assert proof[module.RUNTIME_MODULE_RELATIVE.as_posix()][2] == runtime_module_bytes
    assert client.paths[0].endswith("/branches/main")
    assert all(path.startswith(f"/repos/{module.SOURCE_REPOSITORY}/") for path in client.paths)


def test_public_exact_current_pair_wrong_mode_blob_or_content_fails_closed():
    module = load_broker()
    source_sha = "a" * 40
    adapter_bytes = b"#!/usr/bin/env python3\n# adapter\n"
    runtime_module_bytes = b"# runtime module\n"

    cases = (
        {"adapter_mode": "100644"},
        {"adapter_tree_blob": "d" * 40},
        {"adapter_content_bytes": b"different bytes\n"},
        {"runtime_module_mode": "100755"},
        {"runtime_module_tree_blob": "e" * 40},
        {"runtime_module_content_bytes": b"different module\n"},
        {"tree_truncated": True},
    )
    for overrides in cases:
        client = FakeGitHub(
            public_payloads(
                module,
                source_sha=source_sha,
                adapter_bytes=adapter_bytes,
                runtime_module_bytes=runtime_module_bytes,
                **overrides,
            )
        )
        try:
            module._exact_current_runtime_pair(client)
        except module.BootstrapReachabilityError:
            pass
        else:
            raise AssertionError(f"public proof drift must fail closed: {overrides}")


def test_end_to_end_lagging_clean_manager_succeeds_when_runtime_pair_is_exact_current():
    module = load_broker()
    uid = os.getuid()
    gid = os.getgid()
    source_sha = "a" * 40
    manager_head = "b" * 40

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        trusted = root / "trusted"
        manager_home = root / "home"
        manager = manager_home / "RPi5_main"
        installed = root / "installed-entrypoint"
        dispatch = trusted / module.STALE_DISPATCH_RELATIVE
        adapter = manager / module.RUNTIME_RELATIVE
        runtime_module = manager / module.RUNTIME_MODULE_RELATIVE

        dispatch.parent.mkdir(parents=True)
        adapter.parent.mkdir(parents=True)
        runtime_module.parent.mkdir(parents=True)
        manager_home.mkdir(exist_ok=True)
        trusted.chmod(0o755)
        manager.chmod(0o755)

        installed_bytes = b"known stale entrypoint\n"
        stale_dispatch_bytes = b"known stale dispatch without refresh route\n"
        adapter_bytes = (
            b'BOOTSTRAP_INTERFACE = "'
            + module.BOOTSTRAP_INTERFACE.encode("ascii")
            + b'"\n'
            + b"def run_from_bootstrap(issue_number):\n"
            + b'    return {"result": "PASS", "issue": issue_number, "transport": "bootstrap"}\n'
        )
        runtime_module_bytes = b"# exact-current refresh runtime module\nVALUE = 1\n"

        installed.write_bytes(installed_bytes)
        installed.chmod(0o755)
        dispatch.write_bytes(stale_dispatch_bytes)
        dispatch.chmod(0o644)
        adapter.write_bytes(adapter_bytes)
        adapter.chmod(0o755)
        runtime_module.write_bytes(runtime_module_bytes)
        runtime_module.chmod(0o644)

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

        adapter_blob = module._git_blob_sha1(adapter_bytes)
        runtime_module_blob = module._git_blob_sha1(runtime_module_bytes)
        client = FakeGitHub(
            public_payloads(
                module,
                source_sha=source_sha,
                adapter_bytes=adapter_bytes,
                runtime_module_bytes=runtime_module_bytes,
            )
        )

        def fake_runner(argv, **kwargs):
            argv = tuple(argv)
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
                    return result(argv, manager_head + "\n")
                if args == ("status", "--porcelain", "--untracked-files=all"):
                    return result(argv, "")
                if args == ("remote", "get-url", "origin"):
                    return result(argv, module.REVIEWED_ORIGIN + "\n")
                if args == ("ls-tree", manager_head, "--", module.RUNTIME_RELATIVE.as_posix()):
                    return result(
                        argv,
                        f"100755 blob {adapter_blob}\t{module.RUNTIME_RELATIVE.as_posix()}\n",
                    )
                if args == ("ls-tree", manager_head, "--", module.RUNTIME_MODULE_RELATIVE.as_posix()):
                    return result(
                        argv,
                        f"100644 blob {runtime_module_blob}\t{module.RUNTIME_MODULE_RELATIVE.as_posix()}\n",
                    )
            raise AssertionError(f"unexpected git call: {argv}")

        account = SimpleNamespace(pw_uid=uid, pw_gid=gid, pw_dir=str(manager_home))
        try:
            receipt = module.execute(
                123,
                runner=fake_runner,
                pwd_lookup=lambda name: account if name == module.MANAGER_USERNAME else None,
                github_client=client,
            )
        finally:
            module.os.geteuid = original_geteuid

        assert source_sha != manager_head
        assert receipt == {"result": "PASS", "issue": 123, "transport": "bootstrap"}


def test_manager_pair_blob_or_worktree_drift_fails_closed_before_runtime_entry():
    module = load_broker()
    uid = os.getuid()
    gid = os.getgid()
    manager_head = "b" * 40
    adapter_bytes = b"adapter exact\n"
    runtime_module_bytes = b"module exact\n"
    exact_pair = {
        module.RUNTIME_RELATIVE.as_posix(): (
            "100755",
            module._git_blob_sha1(adapter_bytes),
            adapter_bytes,
        ),
        module.RUNTIME_MODULE_RELATIVE.as_posix(): (
            "100644",
            module._git_blob_sha1(runtime_module_bytes),
            runtime_module_bytes,
        ),
    }

    for drift in ("adapter_blob", "adapter_bytes", "module_blob", "module_bytes"):
        with tempfile.TemporaryDirectory() as td:
            manager = Path(td) / "RPi5_main"
            adapter = manager / module.RUNTIME_RELATIVE
            runtime_module = manager / module.RUNTIME_MODULE_RELATIVE
            adapter.parent.mkdir(parents=True)
            runtime_module.parent.mkdir(parents=True)
            adapter.write_bytes(
                b"adapter drift\n" if drift == "adapter_bytes" else adapter_bytes
            )
            adapter.chmod(0o755)
            runtime_module.write_bytes(
                b"module drift\n" if drift == "module_bytes" else runtime_module_bytes
            )
            runtime_module.chmod(0o644)

            def fake_runner(argv, **kwargs):
                argv = tuple(argv)
                git_index = argv.index("/usr/bin/git")
                args = argv[git_index + 4 :]
                if args == ("rev-parse", "HEAD"):
                    return result(argv, manager_head + "\n")
                if args == ("status", "--porcelain", "--untracked-files=all"):
                    return result(argv, "")
                if args == ("remote", "get-url", "origin"):
                    return result(argv, module.REVIEWED_ORIGIN + "\n")
                if args == ("ls-tree", manager_head, "--", module.RUNTIME_RELATIVE.as_posix()):
                    blob = (
                        "d" * 40
                        if drift == "adapter_blob"
                        else exact_pair[module.RUNTIME_RELATIVE.as_posix()][1]
                    )
                    return result(
                        argv,
                        f"100755 blob {blob}\t{module.RUNTIME_RELATIVE.as_posix()}\n",
                    )
                if args == ("ls-tree", manager_head, "--", module.RUNTIME_MODULE_RELATIVE.as_posix()):
                    blob = (
                        "e" * 40
                        if drift == "module_blob"
                        else exact_pair[module.RUNTIME_MODULE_RELATIVE.as_posix()][1]
                    )
                    return result(
                        argv,
                        f"100644 blob {blob}\t{module.RUNTIME_MODULE_RELATIVE.as_posix()}\n",
                    )
                raise AssertionError(f"unexpected Git call: {argv}")

            try:
                module._manager_runtime_pair(
                    manager,
                    uid,
                    gid,
                    exact_pair,
                    runner=fake_runner,
                )
            except module.BootstrapReachabilityError:
                pass
            else:
                raise AssertionError(f"manager drift must fail closed: {drift}")


def test_manager_origin_dirty_and_snapshot_drift_still_fail_closed():
    module = load_broker()
    manager = Path("/nonexistent-test-manager")
    head_a = "a" * 40
    head_b = "b" * 40

    def dirty_runner(argv, **kwargs):
        argv = tuple(argv)
        args = argv[argv.index("/usr/bin/git") + 4 :]
        if args == ("rev-parse", "HEAD"):
            return result(argv, head_a + "\n")
        if args == ("status", "--porcelain", "--untracked-files=all"):
            return result(argv, " M changed\n")
        if args == ("remote", "get-url", "origin"):
            return result(argv, module.REVIEWED_ORIGIN + "\n")
        raise AssertionError(args)

    try:
        module._manager_snapshot(manager, runner=dirty_runner)
    except module.BootstrapReachabilityError as exc:
        assert "not clean" in str(exc)
    else:
        raise AssertionError("dirty manager must fail closed")

    def origin_runner(argv, **kwargs):
        argv = tuple(argv)
        args = argv[argv.index("/usr/bin/git") + 4 :]
        if args == ("rev-parse", "HEAD"):
            return result(argv, head_a + "\n")
        if args == ("status", "--porcelain", "--untracked-files=all"):
            return result(argv, "")
        if args == ("remote", "get-url", "origin"):
            return result(argv, "https://example.invalid/not-reviewed.git\n")
        raise AssertionError(args)

    try:
        module._manager_snapshot(manager, runner=origin_runner)
    except module.BootstrapReachabilityError as exc:
        assert "origin drifted" in str(exc)
    else:
        raise AssertionError("wrong manager origin must fail closed")

    calls = {"head": 0}
    adapter_bytes = b"adapter exact\n"
    runtime_module_bytes = b"module exact\n"
    exact_pair = {
        module.RUNTIME_RELATIVE.as_posix(): (
            "100755",
            module._git_blob_sha1(adapter_bytes),
            adapter_bytes,
        ),
        module.RUNTIME_MODULE_RELATIVE.as_posix(): (
            "100644",
            module._git_blob_sha1(runtime_module_bytes),
            runtime_module_bytes,
        ),
    }
    with tempfile.TemporaryDirectory() as td:
        manager = Path(td) / "RPi5_main"
        adapter = manager / module.RUNTIME_RELATIVE
        runtime_module = manager / module.RUNTIME_MODULE_RELATIVE
        adapter.parent.mkdir(parents=True)
        runtime_module.parent.mkdir(parents=True)
        adapter.write_bytes(adapter_bytes)
        adapter.chmod(0o755)
        runtime_module.write_bytes(runtime_module_bytes)
        runtime_module.chmod(0o644)

        def drift_runner(argv, **kwargs):
            argv = tuple(argv)
            args = argv[argv.index("/usr/bin/git") + 4 :]
            if args == ("rev-parse", "HEAD"):
                calls["head"] += 1
                return result(argv, (head_a if calls["head"] == 1 else head_b) + "\n")
            if args == ("status", "--porcelain", "--untracked-files=all"):
                return result(argv, "")
            if args == ("remote", "get-url", "origin"):
                return result(argv, module.REVIEWED_ORIGIN + "\n")
            if args == ("ls-tree", head_a, "--", module.RUNTIME_RELATIVE.as_posix()):
                return result(
                    argv,
                    f"100755 blob {exact_pair[module.RUNTIME_RELATIVE.as_posix()][1]}\t{module.RUNTIME_RELATIVE.as_posix()}\n",
                )
            if args == ("ls-tree", head_a, "--", module.RUNTIME_MODULE_RELATIVE.as_posix()):
                return result(
                    argv,
                    f"100644 blob {exact_pair[module.RUNTIME_MODULE_RELATIVE.as_posix()][1]}\t{module.RUNTIME_MODULE_RELATIVE.as_posix()}\n",
                )
            raise AssertionError(args)

        try:
            module._manager_runtime_pair(
                manager,
                os.getuid(),
                os.getgid(),
                exact_pair,
                runner=drift_runner,
            )
        except module.BootstrapReachabilityError as exc:
            assert "snapshot drifted" in str(exc)
        else:
            raise AssertionError("manager snapshot drift must fail closed")


def test_broker_is_identity_only_and_has_no_manager_mutation_primitive():
    source = BROKER.read_text(encoding="utf-8")
    assert 'parser.add_argument("--issue-number"' in source
    assert "from deploy_executor.weather_private_privileged_dispatch" not in source
    assert "import deploy_executor.weather_private_privileged_dispatch" not in source
    assert "shell=False" in source
    assert "/usr/sbin/runuser" in source
    assert "api.github.com" in source
    assert '"Authorization"' not in source
    assert "ls-remote" not in source
    assert "git fetch" not in source
    assert "git checkout" not in source
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
    test_failure_receipt_exposes_only_allowlisted_preconsume_telemetry()
    test_public_exact_current_pair_verifies_commit_tree_modes_blobs_and_contents()
    test_public_exact_current_pair_wrong_mode_blob_or_content_fails_closed()
    test_end_to_end_lagging_clean_manager_succeeds_when_runtime_pair_is_exact_current()
    test_manager_pair_blob_or_worktree_drift_fails_closed_before_runtime_entry()
    test_manager_origin_dirty_and_snapshot_drift_still_fail_closed()
    test_broker_is_identity_only_and_has_no_manager_mutation_primitive()
    print("WeatherNext installer-boundary bootstrap tests: PASS")
