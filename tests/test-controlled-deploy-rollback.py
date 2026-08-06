#!/usr/bin/env python3
"""Regression tests for compensated V12 manual rollback."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile


REPO = pathlib.Path(__file__).resolve().parents[1]


def run(
    args: list[str],
    *,
    cwd: pathlib.Path,
    env: dict[str, str],
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if expect_success and result.returncode:
        raise AssertionError(f"command failed: {args}\n{result.stdout}")
    if not expect_success and result.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {args}\n{result.stdout}")
    return result


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mode(path: pathlib.Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def copy(relative: str, fake_repo: pathlib.Path) -> None:
    destination = fake_repo / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / relative, destination)


def assert_deployed(fake_repo: pathlib.Path, fake_root: pathlib.Path) -> None:
    pairs = {
        "ops/bin/rpi5-backup": "usr/local/sbin/rpi5-backup",
        "ops/cron.d/rpi5-backup": "etc/cron.d/rpi5-backup",
        "ops/logrotate.d/rpi5-backup": "etc/logrotate.d/rpi5-backup",
    }
    for source, target in pairs.items():
        assert sha256(fake_repo / source) == sha256(fake_root / target)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="rpi5-deploy-rollback-") as raw:
        work = pathlib.Path(raw)
        fake_repo = work / "repo"
        fake_root = work / "root"
        state = work / "state"
        log = work / "deploy.log"

        for relative in (
            "scripts/rpi5-deploy",
            "scripts/rpi5_deploy.py",
            "scripts/rpi5_deploy_lib.py",
            "scripts/rpi5_deploy_tx.py",
            "ops/deploy/targets.json",
            "ops/bin/rpi5-backup",
            "ops/cron.d/rpi5-backup",
            "ops/logrotate.d/rpi5-backup",
            "ops/backup/rpi5-backup.conf.example",
            "baselines/runtime/current.json",
        ):
            copy(relative, fake_repo)

        live = {
            "backup-runner": fake_root / "usr/local/sbin/rpi5-backup",
            "backup-cron": fake_root / "etc/cron.d/rpi5-backup",
            "backup-logrotate": fake_root / "etc/logrotate.d/rpi5-backup",
        }
        for path in live.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        live["backup-runner"].write_text("old runner\n", encoding="utf-8")
        live["backup-cron"].write_text("old cron\n", encoding="utf-8")
        live["backup-logrotate"].write_text("old rotate\n", encoding="utf-8")
        os.chmod(live["backup-runner"], 0o700)
        os.chmod(live["backup-cron"], 0o644)
        os.chmod(live["backup-logrotate"], 0o644)
        before = {
            key: (path.read_bytes(), mode(path))
            for key, path in live.items()
        }

        run(["git", "init", "-q", "-b", "main"], cwd=fake_repo, env=os.environ.copy())
        run(["git", "config", "user.name", "test"], cwd=fake_repo, env=os.environ.copy())
        run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=fake_repo,
            env=os.environ.copy(),
        )
        run(["git", "add", "--all"], cwd=fake_repo, env=os.environ.copy())
        run(["git", "commit", "-q", "-m", "test"], cwd=fake_repo, env=os.environ.copy())
        short_commit = run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=fake_repo,
            env=os.environ.copy(),
        ).stdout.strip()

        env = os.environ.copy()
        env.update({
            "RPI5_DEPLOY_TEST_MODE": "1",
            "RPI5_DEPLOY_TEST_SANDBOX": str(work),
            "RPI5_DEPLOY_ROOT": str(fake_root),
            "RPI5_DEPLOY_STATE_DIR": str(state),
            "RPI5_DEPLOY_LOG": str(log),
            "RPI5_DEPLOY_MAX_PLAN_AGE": "300",
        })
        controller = ["bash", str(fake_repo / "scripts/rpi5-deploy")]

        run([*controller, "plan"], cwd=fake_repo, env=env)
        run(
            [*controller, "deploy", "--confirm", short_commit],
            cwd=fake_repo,
            env=env,
        )
        assert_deployed(fake_repo, fake_root)

        txid = (state / "latest-success").read_text(encoding="utf-8").strip()
        transaction_dir = state / "transactions" / txid
        metadata_path = transaction_dir / "transaction.json"

        cron_backup = transaction_dir / "backups/backup-cron.before"
        saved_cron_backup = cron_backup.read_bytes()
        cron_backup.write_bytes(b"corrupted rollback backup\n")
        os.chmod(cron_backup, 0o600)
        failed = run(
            [*controller, "rollback", "--latest", "--confirm", "ROLLBACK"],
            cwd=fake_repo,
            env=env,
            expect_success=False,
        )
        assert "private snapshot checksum mismatch: backup-cron.before" in failed.stdout
        assert_deployed(fake_repo, fake_root)
        assert json.loads(metadata_path.read_text(encoding="utf-8"))["status"] == "success"
        cron_backup.write_bytes(saved_cron_backup)
        os.chmod(cron_backup, 0o600)

        compensated_env = env.copy()
        compensated_env["RPI5_DEPLOY_TEST_FAIL_MANUAL_AFTER"] = "backup-cron"
        failed = run(
            [*controller, "rollback", "--latest", "--confirm", "ROLLBACK"],
            cwd=fake_repo,
            env=compensated_env,
            expect_success=False,
        )
        assert "manual rollback failed; deployed state was restored" in failed.stdout
        assert_deployed(fake_repo, fake_root)
        compensated = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert compensated["status"] == "success"
        assert compensated["rollback_attempt_status"] == "compensated"
        assert (state / "latest-success").read_text(encoding="utf-8").strip() == txid

        run(
            [*controller, "rollback", "--latest", "--confirm", "ROLLBACK"],
            cwd=fake_repo,
            env=env,
        )
        for key, path in live.items():
            expected_bytes, expected_mode = before[key]
            assert path.read_bytes() == expected_bytes
            assert mode(path) == expected_mode
        completed = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert completed["status"] == "manually_rolled_back"
        assert completed["rollback_attempt_status"] == "success"
        assert not (state / "latest-success").exists()

    print("V12 compensated manual rollback regression: PASS")


if __name__ == "__main__":
    main()
