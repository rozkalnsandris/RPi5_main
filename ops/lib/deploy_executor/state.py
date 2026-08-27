from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

STATES: Final = frozenset(
    {
        "DISCOVERED",
        "VALIDATING",
        "ACCEPTED",
        "CONSUMED",
        "VERIFYING",
        "SUCCEEDED",
        "REJECTED",
        "EXPIRED",
        "STOP_ERROR",
    }
)

TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "DISCOVERED": frozenset({"VALIDATING"}),
    "VALIDATING": frozenset({"ACCEPTED", "REJECTED", "EXPIRED", "STOP_ERROR"}),
    "ACCEPTED": frozenset({"CONSUMED", "REJECTED", "EXPIRED", "STOP_ERROR"}),
    "CONSUMED": frozenset({"VERIFYING", "STOP_ERROR"}),
    "VERIFYING": frozenset({"SUCCEEDED", "STOP_ERROR"}),
    "SUCCEEDED": frozenset(),
    "REJECTED": frozenset(),
    "EXPIRED": frozenset(),
    "STOP_ERROR": frozenset(),
}

STATE_DB_APPLICATION_ID: Final = 1381647448  # ASCII-ish "RZDX"
STATE_DB_SCHEMA_VERSION: Final = 1
EXPECTED_COLUMNS: Final = (
    ("repository_id", "INTEGER", 1, 1),
    ("issue_id", "INTEGER", 1, 2),
    ("request_id", "TEXT", 1, 0),
    ("canonical_payload_sha256", "TEXT", 1, 0),
    ("raw_body_sha256", "TEXT", 1, 0),
    ("state", "TEXT", 1, 0),
    ("created_at", "TEXT", 1, 0),
    ("updated_at", "TEXT", 1, 0),
    ("consumed_at", "TEXT", 0, 0),
)


class StateError(RuntimeError):
    pass


class StateIntegrityError(StateError):
    pass


class ReplayError(StateError):
    pass


class InvalidTransition(StateError):
    pass


@dataclass(frozen=True)
class RequestRecord:
    repository_id: int
    issue_id: int
    request_id: str
    canonical_payload_sha256: str
    raw_body_sha256: str
    state: str
    created_at: str
    updated_at: str
    consumed_at: str | None


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


class StateStore:
    """Durable replay state.

    Normal runtime opens an already-bootstrapped database. A missing database is
    fail-closed. `bootstrap=True` is installation/recovery-only and refuses to
    overwrite an existing path, so ordinary runtime cannot silently turn state
    loss into a fresh replay window.
    """

    def __init__(self, path: str | Path, *, bootstrap: bool = False):
        self.path = str(path)
        if self.path == ":memory:":
            raise StateIntegrityError("in-memory state is forbidden for durable replay protection")

        path_obj = Path(self.path)
        exists = path_obj.exists()
        if bootstrap and exists:
            raise StateIntegrityError("bootstrap refuses an existing state database")
        if not bootstrap and not exists:
            raise StateIntegrityError("state database is missing; mutation path must remain disabled")

        self._db: sqlite3.Connection | None = None
        try:
            self._db = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys = ON")
            if bootstrap:
                self._db.execute("PRAGMA journal_mode = WAL")
                self._db.execute("PRAGMA synchronous = FULL")
                self._initialize_schema()
            else:
                self._verify_integrity()
                self._db.execute("PRAGMA journal_mode = WAL")
                self._db.execute("PRAGMA synchronous = FULL")
        except StateIntegrityError:
            self.close()
            raise
        except sqlite3.DatabaseError as exc:
            self.close()
            raise StateIntegrityError(f"state database is unreadable: {exc}") from exc

    def _initialize_schema(self) -> None:
        assert self._db is not None
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute(
                """
                CREATE TABLE requests (
                    repository_id INTEGER NOT NULL,
                    issue_id INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    canonical_payload_sha256 TEXT NOT NULL,
                    raw_body_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN (
                            'DISCOVERED', 'VALIDATING', 'ACCEPTED', 'CONSUMED',
                            'VERIFYING', 'SUCCEEDED', 'REJECTED', 'EXPIRED', 'STOP_ERROR'
                        )
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    consumed_at TEXT,
                    PRIMARY KEY (repository_id, issue_id),
                    UNIQUE (request_id)
                )
                """
            )
            self._db.execute(f"PRAGMA application_id = {STATE_DB_APPLICATION_ID}")
            self._db.execute(f"PRAGMA user_version = {STATE_DB_SCHEMA_VERSION}")
            self._db.execute("COMMIT")
        except Exception:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        self._verify_integrity()

    def _verify_integrity(self) -> None:
        assert self._db is not None

        quick_check = self._db.execute("PRAGMA quick_check").fetchone()
        if quick_check is None or quick_check[0] != "ok":
            raise StateIntegrityError("SQLite quick_check did not return ok")

        application_id = self._db.execute("PRAGMA application_id").fetchone()[0]
        if application_id != STATE_DB_APPLICATION_ID:
            raise StateIntegrityError("state database application_id mismatch")

        schema_version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if schema_version != STATE_DB_SCHEMA_VERSION:
            raise StateIntegrityError("state database schema version mismatch")

        columns = tuple(
            (row["name"], row["type"], row["notnull"], row["pk"])
            for row in self._db.execute("PRAGMA table_info(requests)").fetchall()
        )
        if columns != EXPECTED_COLUMNS:
            raise StateIntegrityError("state database requests schema mismatch")

        unique_request_id = False
        for index in self._db.execute("PRAGMA index_list(requests)").fetchall():
            if index["unique"] != 1:
                continue
            index_name = str(index["name"]).replace("'", "''")
            index_columns = [
                row["name"]
                for row in self._db.execute(f"PRAGMA index_info('{index_name}')").fetchall()
            ]
            if index_columns == ["request_id"]:
                unique_request_id = True
                break
        if not unique_request_id:
            raise StateIntegrityError("state database request_id uniqueness constraint is missing")

        for row in self._db.execute(
            """
            SELECT repository_id, issue_id, request_id,
                   canonical_payload_sha256, raw_body_sha256,
                   state, consumed_at
            FROM requests
            """
        ).fetchall():
            if row["repository_id"] < 1 or row["issue_id"] < 1:
                raise StateIntegrityError("state database contains invalid GitHub identity")
            if not _is_uuid4(row["request_id"]):
                raise StateIntegrityError("state database contains invalid request_id")
            if not _is_sha256(row["canonical_payload_sha256"]) or not _is_sha256(
                row["raw_body_sha256"]
            ):
                raise StateIntegrityError("state database contains invalid digest")
            if row["state"] not in STATES:
                raise StateIntegrityError("state database contains unknown state")
            if row["state"] in {"CONSUMED", "VERIFYING", "SUCCEEDED"} and row["consumed_at"] is None:
                raise StateIntegrityError("consumed state is missing consumed_at")
            if row["state"] in {"DISCOVERED", "VALIDATING", "ACCEPTED", "REJECTED", "EXPIRED"} and row[
                "consumed_at"
            ] is not None:
                raise StateIntegrityError("pre-consumption state unexpectedly has consumed_at")

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def discover(
        self,
        *,
        repository_id: int,
        issue_id: int,
        request_id: str,
        canonical_payload_sha256: str,
        raw_body_sha256: str,
    ) -> RequestRecord:
        assert self._db is not None
        if type(repository_id) is not int or repository_id < 1 or type(issue_id) is not int or issue_id < 1:
            raise StateError("repository_id and issue_id must be positive integers")
        if not _is_uuid4(request_id):
            raise StateError("request_id must be canonical UUIDv4")
        if not _is_sha256(canonical_payload_sha256) or not _is_sha256(raw_body_sha256):
            raise StateError("state digests must be lowercase SHA-256 hex")

        now = _now_utc()
        try:
            self._db.execute(
                """
                INSERT INTO requests (
                    repository_id, issue_id, request_id,
                    canonical_payload_sha256, raw_body_sha256, state,
                    created_at, updated_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, 'DISCOVERED', ?, ?, NULL)
                """,
                (
                    repository_id,
                    issue_id,
                    request_id,
                    canonical_payload_sha256,
                    raw_body_sha256,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ReplayError("request or GitHub issue identity was already observed") from exc
        return self.get(request_id)

    def get(self, request_id: str) -> RequestRecord:
        assert self._db is not None
        row = self._db.execute(
            """
            SELECT repository_id, issue_id, request_id,
                   canonical_payload_sha256, raw_body_sha256, state,
                   created_at, updated_at, consumed_at
            FROM requests WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()
        if row is None:
            raise StateError(f"unknown request_id {request_id!r}")
        return RequestRecord(**dict(row))

    def transition(self, request_id: str, new_state: str) -> RequestRecord:
        assert self._db is not None
        if new_state not in STATES:
            raise InvalidTransition(f"unknown state {new_state!r}")

        self._db.execute("BEGIN IMMEDIATE")
        try:
            current = self.get(request_id)
            if new_state not in TRANSITIONS[current.state]:
                raise InvalidTransition(f"{current.state} -> {new_state} is forbidden")
            cursor = self._db.execute(
                "UPDATE requests SET state = ?, updated_at = ? WHERE request_id = ? AND state = ?",
                (new_state, _now_utc(), request_id, current.state),
            )
            if cursor.rowcount != 1:
                raise StateError("state changed concurrently")
            self._db.execute("COMMIT")
        except Exception:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        return self.get(request_id)

    def consume(self, request_id: str) -> RequestRecord:
        assert self._db is not None
        self._db.execute("BEGIN IMMEDIATE")
        try:
            current = self.get(request_id)
            if current.state != "ACCEPTED":
                raise ReplayError(
                    f"authorization cannot enter mutation boundary from state {current.state}"
                )
            now = _now_utc()
            cursor = self._db.execute(
                """
                UPDATE requests
                SET state = 'CONSUMED', updated_at = ?, consumed_at = ?
                WHERE request_id = ? AND state = 'ACCEPTED'
                """,
                (now, now, request_id),
            )
            if cursor.rowcount != 1:
                raise ReplayError("authorization was consumed concurrently")
            self._db.execute("COMMIT")
        except Exception:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        return self.get(request_id)
