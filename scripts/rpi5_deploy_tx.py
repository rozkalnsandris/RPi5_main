#!/usr/bin/env python3
"""Atomic apply and guarded rollback for the RPi5 controlled deploy."""
from __future__ import annotations

import datetime as dt
import grp
import json
import os
import pathlib
import pwd
import re
import shutil
from typing import Any

from rpi5_deploy_lib import (CTX, EXPECTED_REPOSITORY, TRANSACTION_SCHEMA, DeployError,
    Target, append_log, atomic_json, fingerprint, host_preflight, now_iso,
    read_manifest, safe_file, sha256_file, validate_target)


def owner_ids(target: Target) -> tuple[int, int]:
    return (os.getuid(), os.getgid()) if CTX.test_mode else (pwd.getpwnam(target.owner).pw_uid, grp.getgrnam(target.group).gr_gid)


def restore(entry: dict[str, Any], directory: pathlib.Path) -> None:
    target = CTX.rooted(entry["target"])
    before = entry["before"]
    if not before["exists"]:
        target.unlink(missing_ok=True)
        return
    backup = directory / entry["backup_relpath"]
    safe_file(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".rpi5-rollback.{entry['id']}.{os.getpid()}"
    try:
        shutil.copyfile(backup, tmp)
        os.chown(tmp, int(before["uid"]), int(before["gid"]))
        os.chmod(tmp, int(before["mode"], 8))
        with tmp.open("rb") as handle: os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def apply_plan(plan: dict[str, Any]) -> pathlib.Path:
    targets, _ = read_manifest()
    by_id = {target.id: target for target in targets}
    txid = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{plan['short_commit']}"
    directory = CTX.state_dir / "transactions" / txid
    directory.mkdir(parents=True, mode=0o700)
    transaction: dict[str, Any] = {"schema": TRANSACTION_SCHEMA, "id": txid,
        "repository": EXPECTED_REPOSITORY, "commit": plan["commit"], "started_at": now_iso(),
        "status": "running", "targets": []}
    atomic_json(directory / "transaction.json", transaction)
    changed: list[dict[str, Any]] = []
    try:
        for row in plan["targets"]:
            target = by_id[row["id"]]
            if row["action"] == "unchanged":
                transaction["targets"].append({**row, "post_sha256": row["source_sha256"], "changed": False})
                continue
            installed, source = CTX.rooted(target.target), CTX.repo / target.source
            installed.parent.mkdir(parents=True, exist_ok=True)
            backup_rel = f"backups/{target.id}.before"
            if row["before"]["exists"]:
                backup = directory / backup_rel
                backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(installed, backup)
                os.chmod(backup, 0o600)
                if sha256_file(backup) != row["before"]["sha256"]:
                    raise DeployError(f"private backup verification failed: {target.id}")
            entry = {**row, "backup_relpath": backup_rel, "changed": True}
            changed.append(entry)
            uid, gid = owner_ids(target)
            tmp = installed.parent / f".rpi5-deploy.{target.id}.{os.getpid()}"
            try:
                shutil.copyfile(source, tmp)
                os.chown(tmp, uid, gid); os.chmod(tmp, target.mode)
                with tmp.open("rb") as handle: os.fsync(handle.fileno())
                validate_target(target, tmp)
                os.replace(tmp, installed)
            finally:
                tmp.unlink(missing_ok=True)
            after = fingerprint(installed)
            if after["sha256"] != row["source_sha256"] or after["mode"] != f"{target.mode:04o}" or after["uid"] != uid or after["gid"] != gid:
                raise DeployError(f"post-install fingerprint mismatch: {target.id}")
            validate_target(target, installed)
            entry.update({"post_sha256": after["sha256"], "post": after})
            transaction["targets"].append(entry)
            if CTX.test_mode and os.environ.get("RPI5_DEPLOY_TEST_FAIL_AFTER") == target.id:
                raise DeployError(f"synthetic post-install failure after {target.id}")
            atomic_json(directory / "transaction.json", transaction)
        host_preflight()
        transaction.update({"status": "success", "completed_at": now_iso()})
        atomic_json(directory / "transaction.json", transaction)
        CTX.latest_success_path.write_text(txid + "\n", encoding="utf-8")
        os.chmod(CTX.latest_success_path, 0o600)
        append_log(f"DEPLOY PASS transaction={txid} commit={plan['short_commit']}")
        return directory
    except Exception as exc:
        append_log(f"DEPLOY FAIL transaction={txid}; automatic rollback starting")
        errors = []
        for entry in reversed(changed):
            try:
                restore(entry, directory)
                if fingerprint(CTX.rooted(entry["target"])) != entry["before"]:
                    raise DeployError("restored fingerprint does not match planned before-state")
            except Exception as rollback_exc:
                errors.append(f"{entry['id']}: {rollback_exc}")
        transaction.update({"status": "rolled_back" if not errors else "rollback_failed",
                            "failed_at": now_iso(), "error": str(exc)[:1000], "rollback_errors": errors})
        atomic_json(directory / "transaction.json", transaction)
        if errors:
            raise DeployError(f"deploy failed and rollback was incomplete: {errors}") from exc
        raise DeployError(f"deploy failed; all changed targets were rolled back: {exc}") from exc


def latest_transaction() -> tuple[pathlib.Path, dict[str, Any]]:
    safe_file(CTX.latest_success_path)
    txid = CTX.latest_success_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d{8}T\d{12}Z-[0-9a-f]{12}", txid):
        raise DeployError("invalid latest-success pointer")
    directory = CTX.state_dir / "transactions" / txid
    data = json.loads((directory / "transaction.json").read_text(encoding="utf-8"))
    if data.get("schema") != TRANSACTION_SCHEMA or data.get("id") != txid:
        raise DeployError("invalid transaction metadata")
    return directory, data


def manual_rollback() -> None:
    directory, transaction = latest_transaction()
    if transaction.get("status") != "success":
        raise DeployError("latest transaction is not an active successful deploy")
    for entry in transaction["targets"]:
        if entry.get("changed") and fingerprint(CTX.rooted(entry["target"]))["sha256"] != entry.get("post_sha256"):
            raise DeployError(f"refusing rollback over later target drift: {entry['id']}")
    for entry in reversed(transaction["targets"]):
        if entry.get("changed"): restore(entry, directory)
    for entry in transaction["targets"]:
        if entry.get("changed") and fingerprint(CTX.rooted(entry["target"])) != entry["before"]:
            raise DeployError(f"rollback verification failed: {entry['id']}")
    transaction.update({"status": "manually_rolled_back", "rolled_back_at": now_iso()})
    atomic_json(directory / "transaction.json", transaction)
    CTX.latest_success_path.unlink(missing_ok=True)
    append_log(f"ROLLBACK PASS transaction={transaction['id']}")
