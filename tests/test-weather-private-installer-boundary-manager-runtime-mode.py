#!/usr/bin/env python3
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap"


def load_bootstrap():
    loader = SourceFileLoader("weathernext_installer_boundary_mode_recovery", str(BOOTSTRAP))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def must_fail(module, call):
    try:
        call()
    except module.BootstrapReachabilityError:
        return
    raise AssertionError("unsafe manager runtime metadata must fail closed")


def test_manager_runtime_mode_contract_is_narrow_and_restrictive():
    module = load_bootstrap()

    for mode in (0o500, 0o550, 0o555, 0o700, 0o750, 0o755):
        assert module._manager_runtime_mode_allowed(mode), oct(mode)

    for mode in (
        0o000,
        0o100,
        0o400,
        0o300,
        0o720,
        0o702,
        0o770,
        0o707,
        0o4755,
        0o2755,
        0o1755,
    ):
        assert not module._manager_runtime_mode_allowed(mode), oct(mode)


def test_manager_runtime_regular_file_guards_and_root_exact_mode_remain_fail_closed():
    module = load_bootstrap()
    uid = os.getuid()
    gid = os.getgid()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runtime = root / "runtime"
        runtime.write_bytes(b"verified runtime\n")
        runtime.chmod(0o700)

        assert module._regular_bytes(
            runtime,
            uid=uid,
            gid=gid,
            mode_check=module._manager_runtime_mode_allowed,
            maximum=1024,
        ) == b"verified runtime\n"

        runtime.chmod(0o400)
        must_fail(
            module,
            lambda: module._regular_bytes(
                runtime,
                uid=uid,
                gid=gid,
                mode_check=module._manager_runtime_mode_allowed,
                maximum=1024,
            ),
        )

        runtime.chmod(0o720)
        must_fail(
            module,
            lambda: module._regular_bytes(
                runtime,
                uid=uid,
                gid=gid,
                mode_check=module._manager_runtime_mode_allowed,
                maximum=1024,
            ),
        )

        runtime.chmod(0o702)
        must_fail(
            module,
            lambda: module._regular_bytes(
                runtime,
                uid=uid,
                gid=gid,
                mode_check=module._manager_runtime_mode_allowed,
                maximum=1024,
            ),
        )

        runtime.chmod(0o700)
        must_fail(
            module,
            lambda: module._regular_bytes(
                runtime,
                uid=uid + 1,
                gid=gid,
                mode_check=module._manager_runtime_mode_allowed,
                maximum=1024,
            ),
        )
        must_fail(
            module,
            lambda: module._regular_bytes(
                runtime,
                uid=uid,
                gid=gid + 1,
                mode_check=module._manager_runtime_mode_allowed,
                maximum=1024,
            ),
        )

        target = root / "target"
        target.write_bytes(b"target\n")
        target.chmod(0o700)
        symlink = root / "symlink"
        symlink.symlink_to(target)
        must_fail(
            module,
            lambda: module._regular_bytes(
                symlink,
                uid=uid,
                gid=gid,
                mode_check=module._manager_runtime_mode_allowed,
                maximum=1024,
            ),
        )

        hardlink = root / "hardlink"
        os.link(runtime, hardlink)
        must_fail(
            module,
            lambda: module._regular_bytes(
                runtime,
                uid=uid,
                gid=gid,
                mode_check=module._manager_runtime_mode_allowed,
                maximum=1024,
            ),
        )
        hardlink.unlink()

        runtime.chmod(0o755)
        assert module._regular_bytes(
            runtime,
            uid=uid,
            gid=gid,
            mode=0o755,
            maximum=1024,
        ) == b"verified runtime\n"
        runtime.chmod(0o700)
        must_fail(
            module,
            lambda: module._regular_bytes(
                runtime,
                uid=uid,
                gid=gid,
                mode=0o755,
                maximum=1024,
            ),
        )


def test_runtime_bytes_accepts_exact_git_100755_with_physical_0700_and_loads_only():
    module = load_bootstrap()
    uid = os.getuid()
    gid = os.getgid()
    source_sha = "a" * 40

    with tempfile.TemporaryDirectory() as td:
        manager = Path(td) / "RPi5_main"
        runtime = manager / module.RUNTIME_RELATIVE
        runtime.parent.mkdir(parents=True)
        runtime_bytes = (
            b'BOOTSTRAP_INTERFACE = "'
            + module.BOOTSTRAP_INTERFACE.encode("ascii")
            + b'"\n'
            + b"RUNTIME_ENTRY_CALLED = False\n"
            + b"def run_from_bootstrap(issue_number):\n"
            + b"    global RUNTIME_ENTRY_CALLED\n"
            + b"    RUNTIME_ENTRY_CALLED = True\n"
            + b'    return {"result": "PASS", "issue": issue_number}\n'
        )
        runtime.write_bytes(runtime_bytes)
        runtime.chmod(0o700)
        runtime_blob = module._git_blob_sha1(runtime_bytes)

        def fake_runner(argv, **kwargs):
            argv = tuple(argv)
            if argv[:2] == ("/usr/bin/git", "ls-remote"):
                return result(f"{source_sha}\trefs/heads/main\n")
            git_index = argv.index("/usr/bin/git")
            git_argv = argv[git_index:]
            assert git_argv[:2] == ("/usr/bin/git", "--no-optional-locks")
            assert git_argv[2] == "-C"
            assert Path(git_argv[3]) == manager
            args = git_argv[4:]
            if args == ("rev-parse", "HEAD"):
                return result(source_sha + "\n")
            if args == ("status", "--porcelain", "--untracked-files=all"):
                return result("")
            if args == ("remote", "get-url", "origin"):
                return result(module.REVIEWED_ORIGIN + "\n")
            if args == ("ls-tree", source_sha, "--", module.RUNTIME_RELATIVE.as_posix()):
                return result(
                    f"100755 blob {runtime_blob}\t{module.RUNTIME_RELATIVE.as_posix()}\n"
                )
            raise AssertionError(f"unexpected git call: {argv}")

        verified_sha, verified_bytes = module._runtime_bytes(
            manager,
            uid,
            gid,
            runner=fake_runner,
        )
        assert verified_sha == source_sha
        assert verified_bytes == runtime_bytes
        entry = module._load_runtime(verified_bytes)
        assert callable(entry)


def test_runtime_bytes_still_rejects_git_mode_blob_origin_dirty_and_main_drift():
    module = load_bootstrap()
    uid = os.getuid()
    gid = os.getgid()
    source_sha = "a" * 40

    with tempfile.TemporaryDirectory() as td:
        manager = Path(td) / "RPi5_main"
        runtime = manager / module.RUNTIME_RELATIVE
        runtime.parent.mkdir(parents=True)
        runtime_bytes = b"print('verified')\n"
        runtime.write_bytes(runtime_bytes)
        runtime.chmod(0o700)
        runtime_blob = module._git_blob_sha1(runtime_bytes)

        def run_case(*, git_mode="100755", blob=runtime_blob, origin=None, dirty=False, remote_sha=None):
            effective_origin = module.REVIEWED_ORIGIN if origin is None else origin
            effective_remote = source_sha if remote_sha is None else remote_sha

            def fake_runner(argv, **kwargs):
                argv = tuple(argv)
                if argv[:2] == ("/usr/bin/git", "ls-remote"):
                    return result(f"{effective_remote}\trefs/heads/main\n")
                git_index = argv.index("/usr/bin/git")
                git_argv = argv[git_index:]
                args = git_argv[4:]
                if args == ("rev-parse", "HEAD"):
                    return result(source_sha + "\n")
                if args == ("status", "--porcelain", "--untracked-files=all"):
                    return result(" M runtime\n" if dirty else "")
                if args == ("remote", "get-url", "origin"):
                    return result(effective_origin + "\n")
                if args == ("ls-tree", source_sha, "--", module.RUNTIME_RELATIVE.as_posix()):
                    return result(
                        f"{git_mode} blob {blob}\t{module.RUNTIME_RELATIVE.as_posix()}\n"
                    )
                raise AssertionError(f"unexpected git call: {argv}")

            module._runtime_bytes(manager, uid, gid, runner=fake_runner)

        must_fail(module, lambda: run_case(git_mode="100644"))
        must_fail(module, lambda: run_case(blob="b" * 40))
        must_fail(module, lambda: run_case(origin="https://example.invalid/wrong.git"))
        must_fail(module, lambda: run_case(dirty=True))
        must_fail(module, lambda: run_case(remote_sha="c" * 40))


if __name__ == "__main__":
    test_manager_runtime_mode_contract_is_narrow_and_restrictive()
    test_manager_runtime_regular_file_guards_and_root_exact_mode_remain_fail_closed()
    test_runtime_bytes_accepts_exact_git_100755_with_physical_0700_and_loads_only()
    test_runtime_bytes_still_rejects_git_mode_blob_origin_dirty_and_main_drift()
    print("WeatherNext manager runtime mode recovery tests: PASS")
