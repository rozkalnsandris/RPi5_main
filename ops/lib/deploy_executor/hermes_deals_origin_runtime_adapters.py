from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid
from typing import Any, Mapping, Sequence

from .hermes_deals_origin_adapter import (
    DISPATCHER_SOURCE_BLOB,
    OPERATION_ID,
    PROBE_SOURCE_BLOB,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_SOURCE_BLOB,
    WORKFLOW_SOURCE_BLOB,
)
from .hermes_deals_origin_host_evidence import (
    BROKER_INSTALL_PATH,
    BROKER_MODE,
    HOST_OBSERVATION_SCHEMA,
    PROBE_PATH,
    PULL_HELPER_MODE,
    REGISTRATION_MODE,
    REGISTRATION_NAME,
    REGISTRATION_PATH,
    ROOT_GROUP,
    ROOT_OWNER,
)
from .hermes_deals_origin_privileged_broker import (
    BROKER_SERVICE_UNIT,
    BROKER_SOCKET_PATH,
    BROKER_SOCKET_UNIT,
)
from .hermes_deals_origin_privileged_dispatcher import INSTALLED_HELPER_PATH
from .hermes_deals_origin_source_auth import (
    SOURCE_CREDENTIAL_GROUP,
    SOURCE_CREDENTIAL_MODE,
    SOURCE_CREDENTIAL_OWNER,
    SOURCE_CREDENTIAL_PATH,
    build_hermes_deals_source_token_provider,
)
from .p9_source_auth import (
    HERMES_DEALS_SOURCE_REPOSITORY,
    HERMES_DEALS_SOURCE_REPOSITORY_ID,
    REQUIRED_PERMISSIONS,
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    AcceptedAuthorization,
)
from .state import (
    EXPECTED_COLUMNS,
    STATE_DB_APPLICATION_ID,
    STATE_DB_SCHEMA_VERSION,
    StateStore,
)

STATE_DB_PATH = Path('/var/lib/rozkalns-deploy-executor-p9/state.sqlite3')
EVIDENCE_ROOT = Path('/var/lib/hermes-deals-audits/origin-path-audit/evidence')
MACHINE_ROOT = EVIDENCE_ROOT / 'rpi5'
SOCKET_PATH = Path(BROKER_SOCKET_PATH)
SOCKET_GROUP = 'rozkalns-deploy-executor'
SOCKET_MODE = 0o660
ROOT_UID = 0
ROOT_GID = 0
MAX_REGISTRATION_BYTES = 4096
MAX_CODE_BYTES = 2 * 1024 * 1024
REVIEWED_HERMES_SOURCE_SHA = 'f6c48cc85c187d927575da6efef4b05b4d4c0e40'
HELPER_SHA256 = '23b29ff5f800cc5ade9cc8e38607a4e37beae9f45c6c82111ea4b49f063e06cf'
PROBE_SHA256 = '96a8b5819ec85f27095c535f1a3be6cba7bac0e2a40a1132869fb39dc669ad43'
BROKER_ENTRYPOINT_GIT_BLOB = '49aced1a1e6dd0c986947f53f06b23eba590aec4'
BROKER_SOCKET_UNIT_GIT_BLOB = '8eb05b83840b13b27e03e2bbb37d6d0bfc3697cb'
BROKER_SERVICE_UNIT_GIT_BLOB = '2f4874323a92610d4d91df719a97688bc880fc48'
BROKER_SOCKET_UNIT_PATH = Path('/etc/systemd/system/rozkalns-hermes-deals-origin-broker.socket')
BROKER_SERVICE_UNIT_PATH = Path('/etc/systemd/system/rozkalns-hermes-deals-origin-broker@.service')
REGISTRATION_FIELDS = frozenset(
    {'schema', 'capability', 'registered_source_sha', 'helper_sha256', 'probe_sha256'}
)
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
UUID4_RE = re.compile(r'^[0-9a-f-]{36}$')


class HermesOriginRuntimeAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class HermesOriginReplayConsumptionReceipt:
    request_id: str
    state: str
    availability_checks: int
    durable_replay_consumed: bool
    replay_mutation_started: bool
    production_mutation_started: bool


@dataclass(frozen=True)
class HermesOriginSourceAppScopeProof:
    repository: str
    repository_id: int
    app_id: int
    installation_id: int
    repository_selection: str
    token_repository_count: int
    permissions: tuple[tuple[str, str], ...]
    credential_content_read: bool
    github_api_request: bool
    installation_token_minted: bool
    installation_token_exposed: bool
    credential_mutation: bool
    filesystem_mutation: bool
    production_mutation_started: bool


def _fail(message: str) -> None:
    raise HermesOriginRuntimeAdapterError(message)


def _metadata(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except FileNotFoundError:
        _fail(f'required runtime target is absent: {path}')


def _require_file(
    path: Path,
    *,
    mode: int,
    uid: int | None = None,
    gid: int | None = None,
    max_bytes: int | None = None,
) -> os.stat_result:
    uid = ROOT_UID if uid is None else uid
    gid = ROOT_GID if gid is None else gid
    meta = _metadata(path)
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        _fail(f'required runtime target is not a single-link regular file: {path}')
    if meta.st_uid != uid or meta.st_gid != gid or stat.S_IMODE(meta.st_mode) != mode:
        _fail(f'required runtime file metadata drifted: {path}')
    if max_bytes is not None and not (0 < meta.st_size <= max_bytes):
        _fail(f'required runtime file size is invalid: {path}')
    return meta


def _require_directory(path: Path, *, mode: int = 0o700) -> os.stat_result:
    meta = _metadata(path)
    if not stat.S_ISDIR(meta.st_mode):
        _fail(f'required runtime target is not a directory: {path}')
    if meta.st_uid != ROOT_UID or meta.st_gid != ROOT_GID or stat.S_IMODE(meta.st_mode) != mode:
        _fail(f'required runtime directory metadata drifted: {path}')
    return meta


def _read_bounded(path: Path, *, max_bytes: int) -> bytes:
    before = _metadata(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        _fail(f'required runtime target is not a single-link regular file: {path}')
    if before.st_size > max_bytes:
        _fail(f'required runtime file exceeds source limit: {path}')
    for required in ('O_NOFOLLOW', 'O_CLOEXEC'):
        if not hasattr(os, required):
            _fail(f'required descriptor guard is unavailable: {required}')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        _fail(f'required runtime file could not be opened safely: {path}')
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail(f'required runtime file changed before descriptor validation: {path}')
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            try:
                chunk = os.read(fd, min(65536, remaining))
            except OSError:
                _fail(f'required runtime file read failed closed: {path}')
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        if len(raw) > max_bytes:
            _fail(f'required runtime file exceeds source limit: {path}')
        try:
            after = os.stat(path, follow_symlinks=False)
        except OSError:
            _fail(f'required runtime file path changed during validation: {path}')
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f'required runtime file changed during descriptor validation: {path}')
        if len(raw) != opened.st_size:
            _fail(f'required runtime file changed while being read: {path}')
        return raw
    finally:
        os.close(fd)


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f'duplicate runtime JSON field is forbidden: {key}')
        result[key] = value
    return result


def _registration() -> Mapping[str, str]:
    _require_file(Path(REGISTRATION_PATH), mode=0o600, max_bytes=MAX_REGISTRATION_BYTES)
    raw = _read_bounded(Path(REGISTRATION_PATH), max_bytes=MAX_REGISTRATION_BYTES)
    try:
        value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _fail('runtime registration is not strict JSON')
    if type(value) is not dict or frozenset(value) != REGISTRATION_FIELDS:
        _fail('runtime registration fields drifted')
    expected = {
        'schema': 'rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1',
        'capability': 'origin-path-audit',
        'registered_source_sha': REVIEWED_HERMES_SOURCE_SHA,
        'helper_sha256': HELPER_SHA256,
        'probe_sha256': PROBE_SHA256,
    }
    if value != expected:
        _fail('runtime registration identity drifted')
    return value


def _group_gid(name: str) -> int:
    try:
        return grp.getgrnam(name).gr_gid
    except KeyError:
        _fail('required runtime group is absent')


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _validate_accepted(accepted: AcceptedAuthorization) -> None:
    if type(accepted) is not AcceptedAuthorization:
        _fail('durable replay adapter requires canonical AcceptedAuthorization')
    if (
        accepted.repository_id != AUTHORIZATION_REPOSITORY_ID
        or accepted.repository_full_name != AUTHORIZATION_REPOSITORY
        or accepted.issue_id < 1
        or accepted.issue_number < 1
    ):
        _fail('durable replay authorization repository identity drifted')
    try:
        parsed = uuid.UUID(accepted.request_id)
    except (ValueError, TypeError, AttributeError):
        _fail('durable replay request_id is invalid')
    if parsed.version != 4 or str(parsed) != accepted.request_id:
        _fail('durable replay request_id is not canonical UUIDv4')
    for digest in (accepted.canonical_payload_sha256, accepted.raw_body_sha256):
        if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
            _fail('durable replay authorization digest is invalid')


def _open_immutable_replay_store() -> sqlite3.Connection:
    _require_file(STATE_DB_PATH, mode=0o600)
    wal = Path(str(STATE_DB_PATH) + '-wal')
    try:
        wal_meta = wal.lstat()
    except FileNotFoundError:
        wal_meta = None
    if wal_meta is not None and wal_meta.st_size != 0:
        _fail('durable replay database has a live WAL')
    uri = f'file:{STATE_DB_PATH}?mode=ro&immutable=1'
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        quick = conn.execute('PRAGMA quick_check').fetchone()
        if quick is None or quick[0] != 'ok':
            _fail('durable replay quick_check failed')
        if conn.execute('PRAGMA application_id').fetchone()[0] != STATE_DB_APPLICATION_ID:
            _fail('durable replay application_id drifted')
        if conn.execute('PRAGMA user_version').fetchone()[0] != STATE_DB_SCHEMA_VERSION:
            _fail('durable replay schema version drifted')
        columns = tuple(
            (row['name'], row['type'], row['notnull'], row['pk'])
            for row in conn.execute('PRAGMA table_info(requests)').fetchall()
        )
        if columns != EXPECTED_COLUMNS:
            _fail('durable replay requests schema drifted')
        return conn
    except HermesOriginRuntimeAdapterError:
        if conn is not None:
            conn.close()
        raise
    except sqlite3.DatabaseError:
        if conn is not None:
            conn.close()
        _fail('durable replay database read failed closed')


def _immutable_replay_available(accepted: AcceptedAuthorization) -> bool:
    conn = _open_immutable_replay_store()
    try:
        rows = conn.execute(
            'SELECT request_id FROM requests '
            'WHERE (repository_id = ? AND issue_id = ?) OR request_id = ? LIMIT 2',
            (accepted.repository_id, accepted.issue_id, accepted.request_id),
        ).fetchall()
        return len(rows) == 0
    except sqlite3.DatabaseError:
        _fail('durable replay availability query failed closed')
    finally:
        conn.close()



class ConcreteDurableHermesOriginReplayAuthority:
    """Read-only availability checks plus one fail-closed durable consume boundary.

    Revalidation may call :meth:`is_available` repeatedly without mutating SQLite.
    A later broker composition may call :meth:`consume` exactly once, but only after
    at least two identical availability checks. This source slice does not wire that
    consume boundary to the installed broker entrypoint.
    """

    def __init__(self):
        self._candidate: AcceptedAuthorization | None = None
        self._availability_checks = 0
        self._terminal = False

    def preflight(self) -> Mapping[str, object]:
        conn = _open_immutable_replay_store()
        conn.close()
        return {
            'durable_replay_adapter_runtime_proven': True,
            'availability_read_only': True,
            'consume_invoked': False,
            'replay_mutation_started': False,
            'production_mutation_started': False,
        }

    def is_available(self, accepted: AcceptedAuthorization) -> bool:
        if self._terminal:
            return False
        _validate_accepted(accepted)
        if self._candidate is not None and accepted != self._candidate:
            _fail('durable replay authorization changed between revalidations')
        available = _immutable_replay_available(accepted)
        if available:
            self._candidate = accepted
            self._availability_checks += 1
        return available

    def consume(self, request_id: str) -> HermesOriginReplayConsumptionReceipt:
        if self._terminal:
            _fail('durable replay consume boundary already entered')
        candidate = self._candidate
        if candidate is None or request_id != candidate.request_id:
            _fail('durable replay consume request has no canonical candidate')
        if self._availability_checks < 2:
            _fail('durable replay consume requires double canonical availability')
        self._terminal = True
        store: StateStore | None = None
        try:
            store = StateStore(STATE_DB_PATH)
            store.discover(
                repository_id=candidate.repository_id,
                issue_id=candidate.issue_id,
                request_id=candidate.request_id,
                canonical_payload_sha256=candidate.canonical_payload_sha256,
                raw_body_sha256=candidate.raw_body_sha256,
            )
            store.transition(candidate.request_id, 'VALIDATING')
            store.transition(candidate.request_id, 'ACCEPTED')
            record = store.consume(candidate.request_id)
        except Exception:
            raise HermesOriginRuntimeAdapterError(
                'durable replay consume failed closed after attempt boundary'
            ) from None
        finally:
            if store is not None:
                store.close()
        if record.state != 'CONSUMED':
            _fail('durable replay consume did not reach CONSUMED')
        return HermesOriginReplayConsumptionReceipt(
            request_id=candidate.request_id,
            state=record.state,
            availability_checks=self._availability_checks,
            durable_replay_consumed=True,
            replay_mutation_started=True,
            production_mutation_started=False,
        )


class ConcreteLocalHermesOriginHostObservationProvider:
    """Collect one fixed sanitized host observation with no caller selectors."""

    def read(self) -> bytes:
        registration = _registration()
        _require_directory(EVIDENCE_ROOT)
        _require_directory(MACHINE_ROOT)

        helper = Path(INSTALLED_HELPER_PATH)
        _require_file(helper, mode=0o755, max_bytes=MAX_CODE_BYTES)
        helper_raw = _read_bounded(helper, max_bytes=MAX_CODE_BYTES)
        if _sha256(helper_raw) != HELPER_SHA256 or _git_blob(helper_raw) != PULL_HELPER_SOURCE_BLOB:
            _fail('installed Hermes pull helper identity drifted')

        probe = Path(PROBE_PATH)
        _require_file(probe, mode=0o755, max_bytes=MAX_CODE_BYTES)
        probe_raw = _read_bounded(probe, max_bytes=MAX_CODE_BYTES)
        if _sha256(probe_raw) != PROBE_SHA256 or _git_blob(probe_raw) != PROBE_SOURCE_BLOB:
            _fail('installed Hermes probe identity drifted')

        broker = Path(BROKER_INSTALL_PATH)
        _require_file(broker, mode=0o755, max_bytes=MAX_CODE_BYTES)
        if _git_blob(_read_bounded(broker, max_bytes=MAX_CODE_BYTES)) != BROKER_ENTRYPOINT_GIT_BLOB:
            _fail('installed Hermes broker entrypoint identity drifted')

        _require_file(BROKER_SOCKET_UNIT_PATH, mode=0o644, max_bytes=MAX_CODE_BYTES)
        if _git_blob(_read_bounded(BROKER_SOCKET_UNIT_PATH, max_bytes=MAX_CODE_BYTES)) != BROKER_SOCKET_UNIT_GIT_BLOB:
            _fail('installed Hermes socket unit identity drifted')
        _require_file(BROKER_SERVICE_UNIT_PATH, mode=0o644, max_bytes=MAX_CODE_BYTES)
        if _git_blob(_read_bounded(BROKER_SERVICE_UNIT_PATH, max_bytes=MAX_CODE_BYTES)) != BROKER_SERVICE_UNIT_GIT_BLOB:
            _fail('installed Hermes service unit identity drifted')

        _require_file(Path(SOURCE_CREDENTIAL_PATH), mode=0o600)
        socket_meta = _metadata(SOCKET_PATH)
        if not stat.S_ISSOCK(socket_meta.st_mode):
            _fail('Hermes broker socket path is not a socket')
        if (
            socket_meta.st_uid != ROOT_UID
            or socket_meta.st_gid != _group_gid(SOCKET_GROUP)
            or stat.S_IMODE(socket_meta.st_mode) != SOCKET_MODE
        ):
            _fail('Hermes broker socket metadata drifted')

        observed = _utc_now()
        observation = {
            'schema': HOST_OBSERVATION_SCHEMA,
            'evidence_id': 'hermes-origin-host-' + observed.strftime('%Y%m%dt%H%M%Sz').lower(),
            'observed_at': observed.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'operation_id': OPERATION_ID,
            'registered_source_sha': registration['registered_source_sha'],
            'registration_path': REGISTRATION_PATH,
            'registration_name': REGISTRATION_NAME,
            'registration_owner': ROOT_OWNER,
            'registration_group': ROOT_GROUP,
            'registration_mode': REGISTRATION_MODE,
            'broker_install_path': BROKER_INSTALL_PATH,
            'broker_owner': ROOT_OWNER,
            'broker_group': ROOT_GROUP,
            'broker_mode': BROKER_MODE,
            'socket_path': BROKER_SOCKET_PATH,
            'socket_unit': BROKER_SOCKET_UNIT,
            'service_unit': BROKER_SERVICE_UNIT,
            'source_credential_path': SOURCE_CREDENTIAL_PATH,
            'source_credential_owner': SOURCE_CREDENTIAL_OWNER,
            'source_credential_group': SOURCE_CREDENTIAL_GROUP,
            'source_credential_mode': SOURCE_CREDENTIAL_MODE,
            'pull_helper_path': INSTALLED_HELPER_PATH,
            'pull_helper_owner': ROOT_OWNER,
            'pull_helper_group': ROOT_GROUP,
            'pull_helper_mode': PULL_HELPER_MODE,
            'pull_helper_source_blob': PULL_HELPER_SOURCE_BLOB,
            'pull_helper_argument_names': list(PULL_HELPER_ARGUMENTS),
            'probe_path': PROBE_PATH,
            'probe_source_blob': PROBE_SOURCE_BLOB,
            'dispatcher_source_blob': DISPATCHER_SOURCE_BLOB,
            'workflow_source_blob': WORKFLOW_SOURCE_BLOB,
            'evidence_read_only': True,
            'credential_content_read': False,
            'protected_values_included': False,
            'filesystem_mutation': False,
            'systemd_interaction': False,
            'authority_expanded': False,
            'production_mutation_started': False,
        }
        return json.dumps(observation, separators=(',', ':'), sort_keys=True).encode('utf-8')


class ConcreteHermesDealsSourceAppScopeProver:
    """Use only the fixed protected Source App key to prove exact read scope.

    Calling :meth:`prove` is a protected operation: the provider signs with the
    private key and mints one short-lived installation token. The token is never
    returned by this interface. Runtime invocation therefore requires a separate
    owner authorization even though it performs no repository or host mutation.
    """

    def prove(self) -> HermesOriginSourceAppScopeProof:
        provider = build_hermes_deals_source_token_provider(
            private_key=SOURCE_CREDENTIAL_PATH,
        )
        provider.get_installation_token()
        if (
            provider.repository != HERMES_DEALS_SOURCE_REPOSITORY
            or provider.repository_id != HERMES_DEALS_SOURCE_REPOSITORY_ID
        ):
            _fail('Hermes Source App provider repository identity drifted')
        return HermesOriginSourceAppScopeProof(
            repository=HERMES_DEALS_SOURCE_REPOSITORY,
            repository_id=HERMES_DEALS_SOURCE_REPOSITORY_ID,
            app_id=SOURCE_APP_ID,
            installation_id=SOURCE_INSTALLATION_ID,
            repository_selection='selected',
            token_repository_count=1,
            permissions=tuple(sorted(REQUIRED_PERMISSIONS.items())),
            credential_content_read=True,
            github_api_request=True,
            installation_token_minted=True,
            installation_token_exposed=False,
            credential_mutation=False,
            filesystem_mutation=False,
            production_mutation_started=False,
        )


def source_readiness() -> Mapping[str, object]:
    return {
        'source_app_scope_prover_implemented': True,
        'source_app_scope_runtime_proven': False,
        'source_app_proof_requires_protected_credential_read': True,
        'source_app_proof_requires_github_api_requests': True,
        'source_app_proof_mints_short_lived_token': True,
        'source_app_token_exposed': False,
        'durable_replay_adapter_implemented': True,
        'durable_replay_availability_read_only': True,
        'durable_replay_consume_implemented': True,
        'durable_replay_runtime_proven': False,
        'host_observation_provider_implemented': True,
        'host_observation_provider_arguments': (),
        'host_observation_runtime_proven': False,
        'credential_content_read_by_host_provider': False,
        'systemd_interaction_by_host_provider': False,
        'broker_entrypoint_wired': False,
        'privileged_dispatch_enabled': False,
        'genuine_hermes_audit_authorized': False,
        'production_mutation_started': False,
    }
