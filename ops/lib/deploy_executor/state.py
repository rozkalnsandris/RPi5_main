from __future__ import annotations

import sqlite3
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


class StateError(RuntimeError):
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


class StateStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._db = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA synchronous = FULL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
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

    def close(self) -> None:
        self._db.close()

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
            self._db.execute("ROLLBACK")
            raise
        return self.get(request_id)

    def consume(self, request_id: str) -> RequestRecord:
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
            self._db.execute("ROLLBACK")
            raise
        return self.get(request_id)
