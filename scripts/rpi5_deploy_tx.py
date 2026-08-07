#!/usr/bin/env python3
"""Atomic apply and guarded rollback for the RPi5 controlled deploy."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import shutil
import stat
import tempfile
from typing import Any

from rpi5_deploy_lib import (CTX, EXPECTED_REPOSITORY, TRANSACTION_SCHEMA, DeployError,
    append_log, atomic_json, fingerprint, fsync_dir, host_preflight, now_iso,
    owner_ids, read_manifest, safe_file, safe_target_parent, secure_dir, sha256_file,
    validate_target)


def sync_file(path: pathlib.Path) -> None:
    with path.open("rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def atomic_text(path: pathlib.Path, text: str) -> None:
    secure_dir(path.parent)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def verify_private_snapshot(path: pathlib.Path, expected_sha256: str, label: str) -> None:
    info = safe_file(path)
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise DeployError(f"private snapshot mode mismatch: {label}")
    if not CTX.test_mode and (info.st_uid != 0 or info.st_gid != 0):
        raise DeployError(f"private snapshot ownership mismatch: {label}")
    if sha256_file(path) != expected_sha256:
        raise DeployError(f"private snapshot checksum mismatch: {label}")


def install_snapshot(
    snapshot: pathlib.Path,
    target: pathlib.Path,
    desired: dict[str, Any],
    label: str,
) -> None:
    verify_private_snapshot(snapshot, str(desired["sha256"]), label)
    safe_target_parent(target)
    temporary = target.parent / f".rpi5-restore.{label}.{os.getpid()}"
    try:
        shutil.copyfile(snapshot, temporary)
        os.chown(temporary, int(desired["uid"]), int(desired["gid"]))
        os.chmod(temporary, int(desired["mode"], 8))
        sync_file(temporary)
        os.replace(temporary, target)
        fsync_dir(target.parent)
    finally:
        temporary.unlink(missing_ok=True)
    if fingerprint(target) != desired:
        raise DeployError(f"restored fingerprint mismatch: {label}")


def restore(entry: dict[str, Any], directory: pathlib.Path) -> None:
    target = CTX.rooted(entry["target"])
    safe_target_parent(target)
    before = entry["before"]
    if not before["exists"]:
        target.unlink(missing_ok=True)
        fsync_dir(target.parent)
        if fingerprint(target) != before:
            raise DeployError(f"restored absence mismatch: {entry['id']}")
        if CTX.test_mode and os.environ.get("RPI5_DEPLOY_TEST_FAIL_RESTORE_AFTER_WRITE") == entry["id"]:
            raise DeployError(f"synthetic restore failure after write: {entry['id']}")
        return
    backup = directory / entry["backup_relpath"]
    install_snapshot(backup, target, before, f"{entry['id']}.before")
    if CTX.test_mode and os.environ.get("RPI5_DEPLOY_TEST_FAIL_RESTORE_AFTER_WRITE") == entry["id"]:
        raise DeployError(f"synthetic restore failure after write: {entry['id']}")


def verify_plan_row_state(row: dict[str, Any], by_id: dict[str, Any]) -> None:
    target = by_id[row["id"]]
    source = CTX.repo / target.source
    safe_file(source)
    if sha256_file(source) != row["source_sha256"]:
        raise DeployError(f"source changed while applying plan: {target.id}")
    installed = CTX.rooted(target.target)
    safe_target_parent(installed)
    if fingerprint(installed) != row["before"]:
        raise DeployError(f"live target changed while applying plan: {target.id}")


def verify_final_state(plan: dict[str, Any], by_id: dict[str, Any]) -> None:
    for row in plan["targets"]:
        target = by_id[row["id"]]
        source = CTX.repo / target.source
        safe_file(source)
        if sha256_file(source) != row["source_sha256"]:
            raise DeployError(f"source changed before transaction commit: {target.id}")
        installed = CTX.rooted(target.target)
        safe_target_parent(installed)
        if fingerprint(installed) != row["desired"]:
            raise DeployError(f"final target fingerprint mismatch: {target.id}")
        validate_target(target, installed)


def apply_plan(plan: dict[str, Any]) -> pathlib.Path:
    targets, _ = read_manifest()
    by_id = {target.id: target for target in targets}
    txid = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{plan['short_commit']}"
    directory = CTX.state_dir / "transactions" / txid
    secure_dir(directory)
    transaction: dict[str, Any] = {"schema": TRANSACTION_SCHEMA, "id": txid,
        "repository": EXPECTED_REPOSITORY, "commit": plan["commit"], "started_at": now_iso(),
        "status": "running", "targets": []}
    atomic_json(directory / "transaction.json", transaction)
    changed: list[dict[str, Any]] = []
    try:
        for row in plan["targets"]:
            target = by_id[row["id"]]
            verify_plan_row_state(row, by_id)
            if row["action"] == "unchanged":
                if row["before"] != row["desired"]:
                    raise DeployError(f"unchanged action has different desired state: {target.id}")
                validate_target(target, CTX.rooted(target.target))
                transaction["targets"].append({**row, "post_sha256": row["source_sha256"],
                                                "post": fingerprint(CTX.rooted(target.target)),
                                                "changed": False, "phase": "unchanged"})
                atomic_json(directory / "transaction.json", transaction)
                continue
            installed, source = CTX.rooted(target.target), CTX.repo / target.source
            safe_target_parent(installed)
            backup_rel = f"backups/{target.id}.before"
            if row["before"]["exists"]:
                backup = directory / backup_rel
                secure_dir(backup.parent)
                shutil.copyfile(installed, backup)
                os.chmod(backup, 0o600)
                sync_file(backup)
                verify_private_snapshot(
                    backup, str(row["before"]["sha256"]), f"{target.id}.before"
                )
            entry = {**row, "backup_relpath": backup_rel, "changed": True, "phase": "prepared"}
            changed.append(entry)
            transaction["targets"].append(entry)
            atomic_json(directory / "transaction.json", transaction)
            uid, gid = owner_ids(target)
            tmp = installed.parent / f".rpi5-deploy.{target.id}.{os.getpid()}"
            try:
                shutil.copyfile(source, tmp)
                os.chown(tmp, uid, gid)
                os.chmod(tmp, target.mode)
                sync_file(tmp)
                validate_target(target, tmp)
                os.replace(tmp, installed)
                fsync_dir(installed.parent)
            finally:
                tmp.unlink(missing_ok=True)
            after = fingerprint(installed)
            if after != row["desired"]:
                raise DeployError(f"post-install fingerprint mismatch: {target.id}")
            validate_target(target, installed)
            entry.update({"post_sha256": after["sha256"], "post": after, "phase": "installed"})
            atomic_json(directory / "transaction.json", transaction)
            if CTX.test_mode and os.environ.get("RPI5_DEPLOY_TEST_FAIL_AFTER") == target.id:
                raise DeployError(f"synthetic post-install failure after {target.id}")
        verify_final_state(plan, by_id)
        host_preflight()
        verify_final_state(plan, by_id)
        transaction.update({"status": "success", "completed_at": now_iso()})
        atomic_json(directory / "transaction.json", transaction)
        atomic_text(CTX.latest_success_path, txid + "\n")
        if CTX.test_mode and os.environ.get("RPI5_DEPLOY_TEST_FAIL_AFTER_POINTER") == "1":
            raise DeployError("synthetic failure after latest-success pointer")
        append_log(f"DEPLOY PASS transaction={txid} commit={plan['short_commit']}")
        return directory
    except Exception as exc:
        try:
            append_log(f"DEPLOY FAIL transaction={txid}; automatic rollback starting")
        except Exception:
            pass
        errors = []
        for entry in reversed(changed):
            try:
                restore(entry, directory)
                if fingerprint(CTX.rooted(entry["target"])) != entry["before"]:
                    raise DeployError("restored fingerprint does not match planned before-state")
                entry["phase"] = "restored"
            except Exception as rollback_exc:
                entry["phase"] = "restore_failed"
                errors.append(f"{entry['id']}: {rollback_exc}")
        try:
            if CTX.latest_success_path.exists():
                safe_file(CTX.latest_success_path)
                if CTX.latest_success_path.read_text(encoding="utf-8").strip() == txid:
                    CTX.latest_success_path.unlink()
                    fsync_dir(CTX.latest_success_path.parent)
        except Exception as pointer_exc:
            errors.append(f"latest-success: {pointer_exc}")
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
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise DeployError("unsafe transaction directory")
    metadata = directory / "transaction.json"
    safe_file(metadata)
    data = json.loads(metadata.read_text(encoding="utf-8"))
    if data.get("schema") != TRANSACTION_SCHEMA or data.get("id") != txid:
        raise DeployError("invalid transaction metadata")
    return directory, data


def create_forward_snapshot(
    entry: dict[str, Any],
    directory: pathlib.Path,
) -> pathlib.Path:
    target = CTX.rooted(entry["target"])
    current = fingerprint(target)
    if current != entry.get("post"):
        raise DeployError(f"refusing rollback over later target drift: {entry['id']}")
    relative = pathlib.Path("rollback-forward") / f"{entry['id']}.post"
    snapshot = directory / relative
    secure_dir(snapshot.parent)
    shutil.copyfile(target, snapshot)
    os.chmod(snapshot, 0o600)
    sync_file(snapshot)
    verify_private_snapshot(snapshot, str(entry["post"]["sha256"]), f"{entry['id']}.post")
    entry["rollback_forward_relpath"] = str(relative)
    return snapshot


def restore_deployed_state(entry: dict[str, Any], directory: pathlib.Path) -> None:
    relative = entry.get("rollback_forward_relpath")
    if not isinstance(relative, str):
        raise DeployError(f"missing rollback compensation snapshot: {entry['id']}")
    install_snapshot(
        directory / relative,
        CTX.rooted(entry["target"]),
        entry["post"],
        f"{entry['id']}.post",
    )


def verify_manual_rollback_inputs(
    transaction: dict[str, Any],
    directory: pathlib.Path,
) -> list[dict[str, Any]]:
    changed = [entry for entry in transaction["targets"] if entry.get("changed")]
    for entry in changed:
        if fingerprint(CTX.rooted(entry["target"])) != entry.get("post"):
            raise DeployError(f"refusing rollback over later target drift: {entry['id']}")
        before = entry["before"]
        if before["exists"]:
            verify_private_snapshot(
                directory / entry["backup_relpath"],
                str(before["sha256"]),
                f"{entry['id']}.before",
            )
    for entry in changed:
        create_forward_snapshot(entry, directory)
    return changed


def manual_rollback() -> None:
    directory, transaction = latest_transaction()
    if transaction.get("status") != "success":
        raise DeployError("latest transaction is not an active successful deploy")
    changed = verify_manual_rollback_inputs(transaction, directory)
    restored: list[dict[str, Any]] = []
    try:
        for entry in reversed(changed):
            restored.append(entry)
            restore(entry, directory)
            if CTX.test_mode and os.environ.get("RPI5_DEPLOY_TEST_FAIL_MANUAL_AFTER") == entry["id"]:
                raise DeployError(f"synthetic manual rollback failure after {entry['id']}")
        for entry in changed:
            if fingerprint(CTX.rooted(entry["target"])) != entry["before"]:
                raise DeployError(f"rollback verification failed: {entry['id']}")
        for entry in changed:
            entry["phase"] = "manually_restored"
        transaction.update({
            "status": "manually_rolled_back",
            "rolled_back_at": now_iso(),
            "rollback_attempt_status": "success",
        })
        atomic_json(directory / "transaction.json", transaction)
        CTX.latest_success_path.unlink(missing_ok=True)
        fsync_dir(CTX.latest_success_path.parent)
        append_log(f"ROLLBACK PASS transaction={transaction['id']}")
    except Exception as exc:
        compensation_errors = []
        for entry in reversed(restored):
            try:
                restore_deployed_state(entry, directory)
                entry["rollback_compensation_phase"] = "deployed_state_restored"
            except Exception as compensation_exc:
                entry["rollback_compensation_phase"] = "restore_failed"
                compensation_errors.append(f"{entry['id']}: {compensation_exc}")
        if not compensation_errors:
            try:
                atomic_text(CTX.latest_success_path, transaction["id"] + "\n")
            except Exception as pointer_exc:
                compensation_errors.append(f"latest-success: {pointer_exc}")
        transaction.update({
            "status": "rollback_failed" if compensation_errors else "success",
            "rollback_attempted_at": now_iso(),
            "rollback_attempt_status": (
                "compensation_failed" if compensation_errors else "compensated"
            ),
            "rollback_error": str(exc)[:1000],
            "rollback_compensation_errors": compensation_errors,
        })
        atomic_json(directory / "transaction.json", transaction)
        if compensation_errors:
            raise DeployError(
                f"manual rollback failed and deployed-state compensation was incomplete: "
                f"{compensation_errors}"
            ) from exc
        raise DeployError(
            f"manual rollback failed; deployed state was restored: {exc}"
        ) from exc
