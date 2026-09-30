from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Iterator, Mapping, Protocol, Sequence
from urllib import request as urllib_request
from urllib.parse import urlsplit

REGISTRY_SCHEMA = "rozkalns.rpi5-main.simple-deploy.targets.v1"
IDENTITY_SCHEMA = "rozkalns.rpi5-main.simple-deploy.identity.v1"
RECEIPT_SCHEMA = "rozkalns.rpi5-main.simple-deploy.receipt.v1"
STATUS_SCHEMA = "rozkalns.rpi5-main.simple-deploy.status.v1"
HOST_CONTRACT = "SIMPLE_DEPLOY_HOST_V1"
HOST_REPOSITORY = "rozkalnsandris/RPi5_main"
SHARED_WORKFLOW_REPOSITORY = "rozkalnsandris/ops-workflows"
ARCHITECTURE = "linux/arm64"
PRODUCTION_TAG = "production"

PRODUCTION_REGISTRY_PATH = Path("/etc/rozkalns-simple-deployer/targets.json")
PRODUCTION_IDENTITY_PATH = Path("/etc/rozkalns-simple-deployer/identity.json")
PRODUCTION_COMPOSE_ROOT = Path("/etc/rozkalns-simple-deployer/compose")
PRODUCTION_STATE_ROOT = Path("/var/lib/rozkalns-simple-deployer")

POINTER_TIMEOUT_SECONDS = 30
IMAGE_METADATA_TIMEOUT_SECONDS = 30
PULL_TIMEOUT_SECONDS = 300
HEALTH_TIMEOUT_SECONDS = 5
COMMAND_GRACE_SECONDS = 30

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
IMAGE_RE = re.compile(r"^ghcr\.io/[a-z0-9][a-z0-9._-]{0,99}/[a-z0-9][a-z0-9._-]{0,99}$")
COMPOSE_FILE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}\.ya?ml$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")

FORBIDDEN_OPERATIONS = (
    "database-schema-data-mutation",
    "destructive-recovery",
    "secrets-credentials-permissions",
    "cloudflare-dns-network",
    "private-provider-activation",
    "unrelated-host-control",
)
PULL_PROFILES = frozenset({"public-anonymous-pull", "private-read-only"})
READINESS_STATES = frozenset({"required", "not-applicable"})

ROOT_KEYS = frozenset({"schema", "schema_version", "execution_enabled", "targets"})
TARGET_KEYS = frozenset({
    "target_alias",
    "consumer_repository",
    "image",
    "architecture",
    "shared_workflow_sha",
    "compose",
    "health",
    "wait_timeout_seconds",
    "receipt_name",
    "persistent_volumes",
    "registry_pull_profile",
    "forbidden_operations",
})
COMPOSE_KEYS = frozenset({"project", "file", "file_sha256", "service"})
HEALTH_KEYS = frozenset({"liveness_url", "readiness_state", "readiness_url"})
IDENTITY_KEYS = frozenset({"schema", "repository", "source_sha"})


class SimpleDeployError(RuntimeError):
    def __init__(self, code: str, message: str, *, mutation_started: bool = False):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.mutation_started = mutation_started


class LockBusy(SimpleDeployError):
    def __init__(self) -> None:
        super().__init__("TARGET_BUSY", "another reconciliation already owns this target")


def _fail(code: str, message: str, *, mutation_started: bool = False) -> None:
    raise SimpleDeployError(code, message, mutation_started=mutation_started)


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], where: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        _fail(
            "REGISTRY_SCHEMA",
            f"{where} keys mismatch; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}",
        )


def _required_string(
    value: Any,
    where: str,
    *,
    max_len: int = 256,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        _fail("REGISTRY_SCHEMA", f"{where} must be a non-empty string <= {max_len} chars")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail("REGISTRY_SCHEMA", f"{where} has invalid format")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_loopback_url(value: Any, where: str) -> str:
    text = _required_string(value, where, max_len=512)
    parsed = urlsplit(text)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        _fail("REGISTRY_POLICY", f"{where} must use fixed http://127.0.0.1 loopback")
    if parsed.username is not None or parsed.password is not None:
        _fail("REGISTRY_POLICY", f"{where} must not contain credentials")
    if parsed.query or parsed.fragment:
        _fail("REGISTRY_POLICY", f"{where} must not contain query or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SimpleDeployError("REGISTRY_POLICY", f"{where} has invalid port") from exc
    if port is None or not 1 <= port <= 65535:
        _fail("REGISTRY_POLICY", f"{where} must include a bounded loopback port")
    if not parsed.path.startswith("/"):
        _fail("REGISTRY_POLICY", f"{where} must contain an absolute HTTP path")
    return text


def _expected_image(repository: str) -> str:
    owner, name = repository.split("/", 1)
    return f"ghcr.io/{owner.lower()}/{name.lower()}"


@dataclass(frozen=True)
class ComposeSpec:
    project: str
    file: str
    file_sha256: str
    service: str


@dataclass(frozen=True)
class HealthSpec:
    liveness_url: str
    readiness_state: str
    readiness_url: str | None


@dataclass(frozen=True)
class TargetSpec:
    target_alias: str
    consumer_repository: str
    image: str
    architecture: str
    shared_workflow_sha: str
    compose: ComposeSpec
    health: HealthSpec
    wait_timeout_seconds: int
    receipt_name: str
    persistent_volumes: tuple[str, ...]
    registry_pull_profile: str
    forbidden_operations: tuple[str, ...]


@dataclass(frozen=True)
class TargetRegistry:
    execution_enabled: bool
    targets: tuple[TargetSpec, ...]

    def get(self, target_alias: str) -> TargetSpec:
        matches = [target for target in self.targets if target.target_alias == target_alias]
        if not matches:
            _fail("UNKNOWN_TARGET", "target alias is not present in the reviewed static registry")
        if len(matches) != 1:
            _fail("AMBIGUOUS_TARGET", "target alias appears more than once")
        return matches[0]


@dataclass(frozen=True)
class DeployerIdentity:
    source_sha: str


def _parse_target(value: Any, index: int) -> TargetSpec:
    where = f"targets[{index}]"
    if type(value) is not dict:
        _fail("REGISTRY_SCHEMA", f"{where} must be an object")
    _exact_keys(value, TARGET_KEYS, where)

    alias = _required_string(value["target_alias"], f"{where}.target_alias", max_len=64, pattern=IDENTIFIER_RE)
    repository = _required_string(
        value["consumer_repository"], f"{where}.consumer_repository", max_len=201, pattern=REPOSITORY_RE
    )
    image = _required_string(value["image"], f"{where}.image", max_len=220, pattern=IMAGE_RE)
    if image != _expected_image(repository):
        _fail("REGISTRY_POLICY", f"{where}.image must be caller-bound to consumer_repository")
    if value["architecture"] != ARCHITECTURE:
        _fail("REGISTRY_POLICY", f"{where}.architecture must be {ARCHITECTURE}")
    shared_sha = _required_string(
        value["shared_workflow_sha"], f"{where}.shared_workflow_sha", max_len=40, pattern=SHA1_RE
    )

    compose = value["compose"]
    if type(compose) is not dict:
        _fail("REGISTRY_SCHEMA", f"{where}.compose must be an object")
    _exact_keys(compose, COMPOSE_KEYS, f"{where}.compose")
    project = _required_string(compose["project"], f"{where}.compose.project", max_len=64, pattern=IDENTIFIER_RE)
    compose_file = _required_string(
        compose["file"], f"{where}.compose.file", max_len=128, pattern=COMPOSE_FILE_RE
    )
    file_sha256 = _required_string(compose["file_sha256"], f"{where}.compose.file_sha256", max_len=64)
    if re.fullmatch(r"[0-9a-f]{64}", file_sha256) is None:
        _fail("REGISTRY_SCHEMA", f"{where}.compose.file_sha256 must be lowercase SHA-256 hex")
    service = _required_string(compose["service"], f"{where}.compose.service", max_len=64, pattern=IDENTIFIER_RE)

    health = value["health"]
    if type(health) is not dict:
        _fail("REGISTRY_SCHEMA", f"{where}.health must be an object")
    _exact_keys(health, HEALTH_KEYS, f"{where}.health")
    liveness_url = _validate_loopback_url(health["liveness_url"], f"{where}.health.liveness_url")
    readiness_state = _required_string(health["readiness_state"], f"{where}.health.readiness_state", max_len=32)
    if readiness_state not in READINESS_STATES:
        _fail("REGISTRY_POLICY", f"{where}.health.readiness_state is unsupported")
    raw_readiness_url = health["readiness_url"]
    if readiness_state == "required":
        readiness_url = _validate_loopback_url(raw_readiness_url, f"{where}.health.readiness_url")
    else:
        if raw_readiness_url is not None:
            _fail("REGISTRY_POLICY", f"{where}.health.readiness_url must be null when not-applicable")
        readiness_url = None

    wait_timeout = value["wait_timeout_seconds"]
    if type(wait_timeout) is not int or not 10 <= wait_timeout <= 300:
        _fail("REGISTRY_POLICY", f"{where}.wait_timeout_seconds must be 10..300")

    receipt_name = _required_string(value["receipt_name"], f"{where}.receipt_name", max_len=140)
    if receipt_name != f"{alias}.json":
        _fail("REGISTRY_POLICY", f"{where}.receipt_name must be exactly {alias}.json")

    volumes = value["persistent_volumes"]
    if type(volumes) is not list or len(volumes) > 32:
        _fail("REGISTRY_SCHEMA", f"{where}.persistent_volumes must be a list with <=32 entries")
    parsed_volumes: list[str] = []
    for volume_index, volume in enumerate(volumes):
        parsed_volumes.append(
            _required_string(
                volume,
                f"{where}.persistent_volumes[{volume_index}]",
                max_len=64,
                pattern=IDENTIFIER_RE,
            )
        )
    if len(parsed_volumes) != len(set(parsed_volumes)):
        _fail("REGISTRY_SCHEMA", f"{where}.persistent_volumes contains duplicates")

    pull_profile = _required_string(value["registry_pull_profile"], f"{where}.registry_pull_profile", max_len=32)
    if pull_profile not in PULL_PROFILES:
        _fail("REGISTRY_POLICY", f"{where}.registry_pull_profile is unsupported")

    forbidden = value["forbidden_operations"]
    if type(forbidden) is not list or tuple(forbidden) != FORBIDDEN_OPERATIONS:
        _fail("REGISTRY_POLICY", f"{where}.forbidden_operations must equal the fixed SIMPLE-DEPLOY exclusion list")

    return TargetSpec(
        target_alias=alias,
        consumer_repository=repository,
        image=image,
        architecture=ARCHITECTURE,
        shared_workflow_sha=shared_sha,
        compose=ComposeSpec(project, compose_file, file_sha256, service),
        health=HealthSpec(liveness_url, readiness_state, readiness_url),
        wait_timeout_seconds=wait_timeout,
        receipt_name=receipt_name,
        persistent_volumes=tuple(parsed_volumes),
        registry_pull_profile=pull_profile,
        forbidden_operations=FORBIDDEN_OPERATIONS,
    )


def load_registry(path: str | Path) -> TargetRegistry:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SimpleDeployError("REGISTRY_READ", "target registry could not be read") from exc
    if type(raw) is not dict:
        _fail("REGISTRY_SCHEMA", "registry root must be an object")
    _exact_keys(raw, ROOT_KEYS, "registry")
    if raw["schema"] != REGISTRY_SCHEMA or raw["schema_version"] != 1:
        _fail("REGISTRY_SCHEMA", "registry schema identity/version mismatch")
    if type(raw["execution_enabled"]) is not bool:
        _fail("REGISTRY_SCHEMA", "registry.execution_enabled must be boolean")
    if type(raw["targets"]) is not list or len(raw["targets"]) > 64:
        _fail("REGISTRY_SCHEMA", "registry.targets must be a list with <=64 entries")
    targets = tuple(_parse_target(item, index) for index, item in enumerate(raw["targets"]))
    aliases = [target.target_alias for target in targets]
    if len(aliases) != len(set(aliases)):
        _fail("REGISTRY_SCHEMA", "target aliases must be unique")
    images = [target.image for target in targets]
    if len(images) != len(set(images)):
        _fail("REGISTRY_SCHEMA", "image identities must be unique across targets")
    return TargetRegistry(execution_enabled=raw["execution_enabled"], targets=targets)


def load_identity(path: str | Path) -> DeployerIdentity:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SimpleDeployError("IDENTITY_READ", "deployer identity could not be read") from exc
    if type(raw) is not dict:
        _fail("IDENTITY_SCHEMA", "identity root must be an object")
    if frozenset(raw) != IDENTITY_KEYS:
        _fail("IDENTITY_SCHEMA", "identity keys mismatch")
    if raw["schema"] != IDENTITY_SCHEMA or raw["repository"] != HOST_REPOSITORY:
        _fail("IDENTITY_SCHEMA", "identity schema or repository mismatch")
    source_sha = raw["source_sha"]
    if type(source_sha) is not str or SHA1_RE.fullmatch(source_sha) is None:
        _fail("IDENTITY_SCHEMA", "identity source_sha must be a full lowercase commit SHA")
    return DeployerIdentity(source_sha=source_sha)

@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], *, timeout_seconds: int) -> CommandResult: ...


class HttpChecker(Protocol):
    def get(self, url: str, *, timeout_seconds: int) -> int: ...


class SubprocessCommandRunner:
    def __init__(self, *, state_root: Path):
        self.state_root = state_root
        self.docker_config = state_root / "docker-anonymous"
        self.docker_config.mkdir(parents=True, exist_ok=True, mode=0o700)

    def run(self, argv: Sequence[str], *, timeout_seconds: int) -> CommandResult:
        if not argv or any(type(item) is not str or not item for item in argv):
            _fail("COMMAND_CONTRACT", "command argv must contain only non-empty strings")
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": str(self.state_root),
            "DOCKER_CONFIG": str(self.docker_config),
        }
        try:
            completed = subprocess.run(
                list(argv),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=timeout_seconds,
                env=env,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            raise SimpleDeployError("COMMAND_FAILED", f"command transport failed: {argv[0]}") from exc
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class LoopbackHttpChecker:
    def __init__(self) -> None:
        self._opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))

    def get(self, url: str, *, timeout_seconds: int) -> int:
        _validate_loopback_url(url, "health url")
        req = urllib_request.Request(
            url,
            method="GET",
            headers={"User-Agent": "rozkalns-simple-deployer/1"},
        )
        try:
            with self._opener.open(req, timeout=timeout_seconds) as response:
                response.read(1)
                return int(response.status)
        except Exception as exc:
            raise SimpleDeployError("HEALTH_FAILED", "loopback health request failed", mutation_started=True) from exc


def _atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
    _atomic_bytes(path, encoded)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SimpleDeployError("STATE_INVALID", f"state file is unreadable: {path.name}") from exc


def _require_private_state_root(path: Path) -> None:
    if not path.is_absolute():
        _fail("STATE_INVALID", "state root must be absolute")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        _fail("STATE_INVALID", "state root must be a real directory")
    if info.st_mode & 0o077:
        _fail("STATE_INVALID", "state root must not be group/world accessible")


def _require_production_file(path: Path, *, mode_mask: int = 0o022) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise SimpleDeployError("INSTALLATION_INVALID", f"required file is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        _fail("INSTALLATION_INVALID", f"required file is not a real regular file: {path}")
    if info.st_uid != 0:
        _fail("INSTALLATION_INVALID", f"required file must be root-owned: {path}")
    if info.st_mode & mode_mask:
        _fail("INSTALLATION_INVALID", f"required file must not be group/world writable: {path}")


class StateStore:
    def __init__(self, root: Path):
        _require_private_state_root(root)
        self.root = root
        self.locks = root / "locks"
        self.receipts = root / "receipts"
        self.status = root / "status"
        self.overrides = root / "overrides"
        for path in (self.locks, self.receipts, self.status, self.overrides):
            path.mkdir(mode=0o700, exist_ok=True)

    @contextmanager
    def lock(self, target_alias: str) -> Iterator[None]:
        lock_path = self.locks / f"{target_alias}.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
        try:
            with os.fdopen(fd, "a+", encoding="utf-8") as handle:
                fd = -1
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise LockBusy() from exc
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            if fd >= 0:
                os.close(fd)

    def status_path(self, target_alias: str) -> Path:
        return self.status / f"{target_alias}.json"

    def receipt_path(self, receipt_name: str) -> Path:
        return self.receipts / receipt_name

    def override_path(self, target_alias: str) -> Path:
        return self.overrides / f"{target_alias}.yaml"

    def last_status(self, target_alias: str) -> Mapping[str, Any] | None:
        value = _read_json(self.status_path(target_alias))
        if value is None:
            return None
        if type(value) is not dict or value.get("schema") != STATUS_SCHEMA or value.get("target_alias") != target_alias:
            _fail("STATE_INVALID", "target status schema or identity mismatch")
        return value

    def last_success(self, target: TargetSpec) -> Mapping[str, Any] | None:
        value = _read_json(self.receipt_path(target.receipt_name))
        if value is None:
            return None
        if type(value) is not dict or value.get("schema") != RECEIPT_SCHEMA:
            _fail("STATE_INVALID", "success receipt schema mismatch")
        if value.get("target_alias") != target.target_alias or value.get("image") != target.image:
            _fail("STATE_INVALID", "success receipt target/image mismatch")
        digest = value.get("deployed_digest")
        if type(digest) is not str or DIGEST_RE.fullmatch(digest) is None:
            _fail("STATE_INVALID", "success receipt digest is invalid")
        return value

    def write_status(self, target_alias: str, payload: Mapping[str, Any]) -> None:
        body = {"schema": STATUS_SCHEMA, "target_alias": target_alias, **payload}
        _atomic_json(self.status_path(target_alias), body)

    def write_success(self, target: TargetSpec, payload: Mapping[str, Any]) -> None:
        body = {"schema": RECEIPT_SCHEMA, "target_alias": target.target_alias, **payload}
        _atomic_json(self.receipt_path(target.receipt_name), body)

    def write_override(self, target: TargetSpec, image_ref: str) -> Path:
        body = {
            "services": {
                target.compose.service: {
                    "image": image_ref,
                }
            }
        }
        path = self.override_path(target.target_alias)
        _atomic_bytes(path, (json.dumps(body, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        return path


@dataclass(frozen=True)
class ImageMetadata:
    digest: str
    source_sha: str
    shared_workflow_sha: str


@dataclass(frozen=True)
class ReconcileResult:
    result: str
    target_alias: str | None
    desired_digest: str | None
    mutation_started: bool
    pointer_changed_during_attempt: bool | None


def _run_required(
    runner: CommandRunner,
    argv: Sequence[str],
    *,
    timeout_seconds: int,
    code: str,
    mutation_started: bool,
) -> str:
    try:
        result = runner.run(argv, timeout_seconds=timeout_seconds)
    except SimpleDeployError as exc:
        raise SimpleDeployError(
            code,
            f"command transport failed: {argv[0]}",
            mutation_started=mutation_started,
        ) from exc
    if result.returncode != 0:
        _fail(code, f"command failed: {argv[0]}", mutation_started=mutation_started)
    return result.stdout


def _parse_manifest_digest(payload: str) -> str:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SimpleDeployError("POINTER_INVALID", "registry manifest metadata is not JSON") from exc
    digest = value.get("digest") if type(value) is dict else None
    if type(digest) is not str or DIGEST_RE.fullmatch(digest) is None:
        _fail("POINTER_INVALID", "production pointer did not resolve to an immutable digest")
    return digest


def _parse_image_metadata(payload: str, target: TargetSpec, desired_digest: str) -> ImageMetadata:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SimpleDeployError("IMAGE_METADATA_INVALID", "image metadata is not JSON") from exc
    if type(value) is not dict:
        _fail("IMAGE_METADATA_INVALID", "image metadata root must be an object")
    if value.get("os") != "linux" or value.get("architecture") != "arm64":
        _fail("IMAGE_METADATA_INVALID", "image platform is not linux/arm64")
    config = value.get("config")
    labels = config.get("Labels") if type(config) is dict else None
    if type(labels) is not dict:
        _fail("IMAGE_METADATA_INVALID", "image labels are missing")
    source_sha = labels.get("org.opencontainers.image.revision")
    target_alias = labels.get("io.rozkalns.simple-deploy.target")
    shared_sha = labels.get("io.rozkalns.simple-deploy.shared-revision")
    if type(source_sha) is not str or SHA1_RE.fullmatch(source_sha) is None:
        _fail("IMAGE_METADATA_INVALID", "consumer source revision label is invalid")
    if target_alias != target.target_alias:
        _fail("IMAGE_METADATA_INVALID", "image target label does not match the reviewed target")
    if shared_sha != target.shared_workflow_sha:
        _fail("IMAGE_METADATA_INVALID", "image shared-workflow revision is not allowlisted for target")
    if not DIGEST_RE.fullmatch(desired_digest):
        _fail("IMAGE_METADATA_INVALID", "desired digest is invalid")
    return ImageMetadata(desired_digest, source_sha, shared_sha)

class SimpleDeployer:
    def __init__(
        self,
        *,
        registry: TargetRegistry,
        identity: DeployerIdentity,
        state: StateStore,
        runner: CommandRunner,
        http: HttpChecker,
        compose_root: Path,
        require_root_owned_compose: bool = False,
    ):
        self.registry = registry
        self.identity = identity
        self.state = state
        self.runner = runner
        self.http = http
        self.compose_root = compose_root
        self.require_root_owned_compose = require_root_owned_compose

    def _status_base(self, target: TargetSpec) -> dict[str, Any]:
        return {
            "timestamp": _canonical_timestamp(),
            "host_contract": HOST_CONTRACT,
            "deployer_repository": HOST_REPOSITORY,
            "deployer_source_sha": self.identity.source_sha,
            "consumer_repository": target.consumer_repository,
            "image": target.image,
        }

    def _verify_compose_file(self, target: TargetSpec) -> Path:
        path = self.compose_root / target.compose.file
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise SimpleDeployError("COMPOSE_CONTRACT_INVALID", "reviewed Compose file is missing") from exc
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            _fail("COMPOSE_CONTRACT_INVALID", "reviewed Compose file must be a real regular file")
        if self.require_root_owned_compose and info.st_uid != 0:
            _fail("COMPOSE_CONTRACT_INVALID", "reviewed Compose file must be root-owned")
        if info.st_mode & 0o022:
            _fail("COMPOSE_CONTRACT_INVALID", "reviewed Compose file must not be group/world writable")
        if _sha256_file(path) != target.compose.file_sha256:
            _fail("COMPOSE_CONTRACT_INVALID", "reviewed Compose file hash drifted")
        return path

    def _resolve_pointer(self, target: TargetSpec) -> str:
        stdout = _run_required(
            self.runner,
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                f"{target.image}:{PRODUCTION_TAG}",
                "--format",
                "{{json .Manifest}}",
            ],
            timeout_seconds=POINTER_TIMEOUT_SECONDS,
            code="POINTER_RESOLUTION_FAILED",
            mutation_started=False,
        )
        return _parse_manifest_digest(stdout)

    def _inspect_image(self, target: TargetSpec, digest: str) -> ImageMetadata:
        stdout = _run_required(
            self.runner,
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                f"{target.image}@{digest}",
                "--format",
                "{{json .Image}}",
            ],
            timeout_seconds=IMAGE_METADATA_TIMEOUT_SECONDS,
            code="IMAGE_METADATA_FAILED",
            mutation_started=False,
        )
        return _parse_image_metadata(stdout, target, digest)

    @staticmethod
    def _compose_prefix(target: TargetSpec, compose_file: Path, override_file: Path) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            target.compose.project,
            "--file",
            str(compose_file),
            "--file",
            str(override_file),
        ]

    def _blocked_by_post_mutation_failure(self, target: TargetSpec) -> bool:
        last_status = self.state.last_status(target.target_alias)
        if last_status is None:
            return False
        return last_status.get("result") == "STOP_ERROR" and last_status.get("mutation_started") is True

    def _write_failure(
        self,
        target: TargetSpec,
        error: SimpleDeployError,
        *,
        desired_digest: str | None,
        source_sha: str | None,
        mutation_started: bool,
    ) -> None:
        self.state.write_status(
            target.target_alias,
            {
                **self._status_base(target),
                "result": "STOP_ERROR" if mutation_started else "PRE_MUTATION_FAILURE",
                "error_code": error.code,
                "mutation_started": mutation_started,
                "blocked": mutation_started,
                "desired_digest": desired_digest,
                "consumer_source_sha": source_sha,
            },
        )

    def reconcile(self, target_alias: str) -> ReconcileResult:
        if not self.registry.execution_enabled:
            return ReconcileResult("DISABLED", None, None, False, None)

        target = self.registry.get(target_alias)
        try:
            with self.state.lock(target.target_alias):
                if self._blocked_by_post_mutation_failure(target):
                    return ReconcileResult("BLOCKED_STOP_ERROR", target.target_alias, None, False, None)
                return self._reconcile_locked(target)
        except LockBusy:
            return ReconcileResult("NO_OP_BUSY", target.target_alias, None, False, None)

    def _reconcile_locked(self, target: TargetSpec) -> ReconcileResult:
        mutation_started = False
        desired_digest: str | None = None
        source_sha: str | None = None
        try:
            if target.registry_pull_profile != "public-anonymous-pull":
                _fail(
                    "PRIVATE_AUTH_NOT_ACTIVATED",
                    "private-read-only registry auth is a separate reviewed profile and is not active",
                )

            compose_file = self._verify_compose_file(target)
            desired_digest = self._resolve_pointer(target)
            image_metadata = self._inspect_image(target, desired_digest)
            source_sha = image_metadata.source_sha
            prior = self.state.last_success(target)
            if prior is not None and prior["deployed_digest"] == desired_digest:
                self.state.write_status(
                    target.target_alias,
                    {
                        **self._status_base(target),
                        "result": "NO_OP_CURRENT",
                        "mutation_started": False,
                        "blocked": False,
                        "desired_digest": desired_digest,
                        "consumer_source_sha": source_sha,
                    },
                )
                return ReconcileResult("NO_OP_CURRENT", target.target_alias, desired_digest, False, False)

            image_ref = f"{target.image}@{desired_digest}"
            override_file = self.state.write_override(target, image_ref)
            prefix = self._compose_prefix(target, compose_file, override_file)

            self.state.write_status(
                target.target_alias,
                {
                    **self._status_base(target),
                    "result": "MUTATION_STARTING",
                    "mutation_started": False,
                    "blocked": False,
                    "desired_digest": desired_digest,
                    "consumer_source_sha": source_sha,
                },
            )

            mutation_started = True
            _run_required(
                self.runner,
                [*prefix, "pull", target.compose.service],
                timeout_seconds=PULL_TIMEOUT_SECONDS,
                code="COMPOSE_PULL_FAILED",
                mutation_started=True,
            )
            _run_required(
                self.runner,
                [
                    *prefix,
                    "up",
                    "-d",
                    "--wait",
                    "--wait-timeout",
                    str(target.wait_timeout_seconds),
                    target.compose.service,
                ],
                timeout_seconds=target.wait_timeout_seconds + COMMAND_GRACE_SECONDS,
                code="COMPOSE_UP_FAILED",
                mutation_started=True,
            )

            container_id = _run_required(
                self.runner,
                [*prefix, "ps", "--quiet", target.compose.service],
                timeout_seconds=30,
                code="CONTAINER_IDENTITY_FAILED",
                mutation_started=True,
            ).strip()
            if CONTAINER_ID_RE.fullmatch(container_id) is None:
                _fail("CONTAINER_IDENTITY_FAILED", "Compose did not return one canonical container id", mutation_started=True)

            running_image = _run_required(
                self.runner,
                ["docker", "inspect", "--format", "{{.Config.Image}}", container_id],
                timeout_seconds=30,
                code="CONTAINER_IDENTITY_FAILED",
                mutation_started=True,
            ).strip()
            if running_image != image_ref:
                _fail(
                    "CONTAINER_IDENTITY_FAILED",
                    "running container is not bound to the frozen immutable image reference",
                    mutation_started=True,
                )

            liveness_status = self.http.get(target.health.liveness_url, timeout_seconds=HEALTH_TIMEOUT_SECONDS)
            if liveness_status != 200:
                _fail("LIVENESS_FAILED", "liveness endpoint did not return 200", mutation_started=True)

            readiness_status: int | None = None
            if target.health.readiness_state == "required":
                assert target.health.readiness_url is not None
                readiness_status = self.http.get(target.health.readiness_url, timeout_seconds=HEALTH_TIMEOUT_SECONDS)
                if readiness_status != 200:
                    _fail("READINESS_FAILED", "readiness endpoint did not return 200", mutation_started=True)

            pointer_after = self._resolve_pointer(target)
            pointer_changed = pointer_after != desired_digest

            success = {
                **self._status_base(target),
                "result": "SUCCESS",
                "deployed_digest": desired_digest,
                "image_ref": image_ref,
                "consumer_source_sha": source_sha,
                "shared_workflow_repository": SHARED_WORKFLOW_REPOSITORY,
                "shared_workflow_sha": image_metadata.shared_workflow_sha,
                "registry_pull_profile": target.registry_pull_profile,
                "compose": {
                    "project": target.compose.project,
                    "file": target.compose.file,
                    "service": target.compose.service,
                    "pull": "PASS",
                    "up_wait": "PASS",
                },
                "health": {
                    "liveness": "PASS",
                    "readiness": "PASS" if readiness_status == 200 else "NOT_APPLICABLE",
                },
                "persistent_volumes": list(target.persistent_volumes),
                "production_pointer": f"{target.image}:{PRODUCTION_TAG}",
                "pointer_digest_before": desired_digest,
                "pointer_digest_after": pointer_after,
                "pointer_changed_during_attempt": pointer_changed,
                "mutation_started": True,
            }
            self.state.write_success(target, success)
            self.state.write_status(
                target.target_alias,
                {
                    **success,
                    "blocked": False,
                },
            )
            return ReconcileResult("SUCCESS", target.target_alias, desired_digest, True, pointer_changed)
        except SimpleDeployError as exc:
            effective_mutation = mutation_started or exc.mutation_started
            self._write_failure(
                target,
                exc,
                desired_digest=desired_digest,
                source_sha=source_sha,
                mutation_started=effective_mutation,
            )
            raise


def _safe_result_line(result: ReconcileResult) -> str:
    parts = [f"result={result.result}"]
    if result.target_alias is not None:
        parts.append(f"target={result.target_alias}")
    if result.desired_digest is not None:
        parts.append(f"digest={result.desired_digest}")
    parts.append(f"mutation_started={'true' if result.mutation_started else 'false'}")
    if result.pointer_changed_during_attempt is not None:
        parts.append(
            "pointer_changed=" + ("true" if result.pointer_changed_during_attempt else "false")
        )
    return "SIMPLE_DEPLOY " + " ".join(parts)


def _production_deployer() -> SimpleDeployer:
    _require_production_file(PRODUCTION_REGISTRY_PATH)
    _require_production_file(PRODUCTION_IDENTITY_PATH)
    registry = load_registry(PRODUCTION_REGISTRY_PATH)
    identity = load_identity(PRODUCTION_IDENTITY_PATH)
    state = StateStore(PRODUCTION_STATE_ROOT)
    docker_config = PRODUCTION_STATE_ROOT / "docker-anonymous" / "config.json"
    if docker_config.exists():
        _fail("AUTH_PROFILE_INVALID", "public anonymous profile refuses Docker credential configuration")
    return SimpleDeployer(
        registry=registry,
        identity=identity,
        state=state,
        runner=SubprocessCommandRunner(state_root=PRODUCTION_STATE_ROOT),
        http=LoopbackHttpChecker(),
        compose_root=PRODUCTION_COMPOSE_ROOT,
        require_root_owned_compose=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile static SIMPLE-DEPLOY v1 targets")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="reconcile all statically reviewed targets")
    group.add_argument("--target", help="reconcile one statically reviewed target alias")
    args = parser.parse_args(argv)

    try:
        deployer = _production_deployer()
        if not deployer.registry.execution_enabled:
            print(_safe_result_line(ReconcileResult("DISABLED", None, None, False, None)))
            return 0

        aliases = (
            [target.target_alias for target in deployer.registry.targets]
            if args.all
            else [args.target]
        )
        failed = False
        for alias in aliases:
            assert alias is not None
            try:
                result = deployer.reconcile(alias)
                print(_safe_result_line(result))
            except SimpleDeployError as exc:
                failed = True
                print(
                    "SIMPLE_DEPLOY "
                    f"result=FAIL target={alias} error_code={exc.code} "
                    f"mutation_started={'true' if exc.mutation_started else 'false'}"
                )
        return 1 if failed else 0
    except SimpleDeployError as exc:
        print(f"SIMPLE_DEPLOY result=FAIL error_code={exc.code} mutation_started=false")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
