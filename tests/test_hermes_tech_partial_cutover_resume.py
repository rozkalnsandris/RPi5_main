from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "ops/bin/hermes-tech-exact-reconcile-v1"
INSTALLER_PATH = ROOT / "ops/bin/install-hermes-tech-simple-deploy-cutover-v1"
RESUME_PATH = ROOT / "ops/bin/hermes-tech-simple-deploy-resume-v1"
CONTRACT_PATH = ROOT / "ops/deploy/hermes-tech-simple-deploy-resume-v1.json"
EXECUTOR_REGISTRY_PATH = ROOT / "ops/deploy/executor-operations.json"


def _load(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


helper = _load("hermes_exact_helper_recovery_test", HELPER_PATH)
installer = _load("hermes_installer_recovery_test", INSTALLER_PATH)
resume = _load("hermes_resume_recovery_test", RESUME_PATH)


class FakeSimpleDeployError(RuntimeError):
    pass


class FakeRegistry:
    def __init__(self, target):
        self.target = target
        self.execution_enabled = True

    def get(self, alias):
        assert alias == helper.TARGET_ALIAS
        return self.target


class FakeBaseDeployer:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def _resolve_pointer(self, target):
        return "sha256:" + "a" * 64

    def _inspect_image(self, target, digest):
        return SimpleNamespace(
            digest=digest,
            source_sha="b" * 40,
            shared_workflow_sha="c" * 40,
        )


def _fake_sd():
    target = SimpleNamespace(
        consumer_repository="rozkalnsandris/hermes-tech",
        image=helper.TARGET_IMAGE,
        compose=SimpleNamespace(
            project=helper.TARGET_PROJECT,
            service=helper.TARGET_SERVICE,
            file="hermes-tech-public.yml",
            file_sha256=helper.EXPECTED_COMPOSE_SHA256,
        ),
        persistent_volumes=(),
        registry_pull_profile="public-anonymous-pull",
    )
    base = FakeBaseDeployer(
        registry=FakeRegistry(target),
        identity=SimpleNamespace(source_sha=helper.COMPATIBLE_DEPLOYER_IDENTITY),
        state=object(),
        runner=object(),
        http=object(),
        compose_root=Path("/tmp"),
        require_root_owned_compose=True,
    )
    return SimpleNamespace(
        SimpleDeployer=FakeBaseDeployer,
        SimpleDeployError=FakeSimpleDeployError,
        _production_deployer=lambda: base,
    ), target


def test_exact_helper_matches_pinned_generic_inspect_signature_without_origin_keyword():
    sd, target = _fake_sd()
    deployer = helper.exact_deployer(sd, "b" * 40, "sha256:" + "a" * 64)

    metadata = deployer._inspect_image(target, "sha256:" + "a" * 64)

    assert metadata.source_sha == "b" * 40


def test_exact_helper_forbids_origin_mode_and_preserves_source_gate():
    sd, target = _fake_sd()
    deployer = helper.exact_deployer(sd, "d" * 40, "sha256:" + "a" * 64)

    with pytest.raises(FakeSimpleDeployError):
        deployer._inspect_image(target, "sha256:" + "a" * 64)
    with pytest.raises(FakeSimpleDeployError):
        deployer._inspect_image(target, "sha256:" + "a" * 64, origin=True)


def test_helper_upgrade_check_is_read_only():
    installer.MUTATION_STARTED = False
    desired = b"new-helper"
    with (
        patch.object(
            installer,
            "helper_upgrade_preflight",
            return_value=(desired, (1, 2, 3, 4), (5, 6, 7, 8)),
        ),
        patch.object(installer, "upgrade_helper_once") as upgrade,
    ):
        assert installer.main([
            "helper-upgrade-check",
            "--expected-main",
            "a" * 40,
        ]) == 0

    upgrade.assert_not_called()
    assert installer.MUTATION_STARTED is False


def test_helper_upgrade_replace_error_preserves_stage_and_baseline(tmp_path):
    installer.MUTATION_STARTED = False
    helper_dest = tmp_path / "hermes-tech-exact-reconcile-v1"
    operator_dest = tmp_path / "hermes-tech-simple-deploy-cutover-v1"
    stage = tmp_path / ".hermes-tech-exact-reconcile-v1.issue1451.stage"
    helper_dest.write_bytes(b"old-helper")
    operator_dest.write_bytes(b"operator")
    desired = b"new-helper"
    helper_identity = (1, 10, 100, len(b"old-helper"))
    operator_identity = (1, 20, 200, len(b"operator"))

    def fake_read(path, *, mode):
        data = path.read_bytes()
        inode = 30 if path == stage else 40 if path == helper_dest else 20
        return (1, inode, 300, len(data)), data

    with (
        patch.object(installer, "HELPER_DEST", helper_dest),
        patch.object(installer, "OPERATOR_DEST", operator_dest),
        patch.object(installer, "HELPER_UPGRADE_STAGE", stage),
        patch.object(
            installer,
            "helper_upgrade_preflight",
            return_value=(desired, helper_identity, operator_identity),
        ),
        patch.object(
            installer,
            "helper_upgrade_preflight_without_stage",
            return_value=(desired, helper_identity, operator_identity),
        ),
        patch.object(installer, "read_installed", side_effect=fake_read),
        patch.object(installer.os, "fchown", return_value=None),
        patch.object(installer.os, "replace", side_effect=OSError("synthetic")),
    ):
        with pytest.raises(
            installer.InstallError,
            match=r"^helper_upgrade_replace_failed$",
        ):
            installer.upgrade_helper_once("a" * 40)

    assert installer.MUTATION_STARTED is True
    assert helper_dest.read_bytes() == b"old-helper"
    assert operator_dest.read_bytes() == b"operator"
    assert stage.read_bytes() == desired


def test_resume_install_check_is_read_only():
    installer.MUTATION_STARTED = False
    with (
        patch.object(installer, "resume_install_preflight", return_value=b"resume"),
        patch.object(installer, "install_once") as install,
    ):
        assert installer.main([
            "resume-install-check",
            "--expected-main",
            "a" * 40,
        ]) == 0

    install.assert_not_called()
    assert installer.MUTATION_STARTED is False


def test_resume_apply_is_forward_only_and_activates_target_timer_last():
    resume.MUTATION_STARTED = False
    calls = []
    fake = SimpleNamespace()
    fake.TARGET_TIMER = "target.timer"
    fake.GLOBAL_TIMER = "global.timer"

    fake.invoke_exact_reconcile = lambda source, digest: calls.append(
        ("reconcile", source, digest)
    )
    fake.verify_new_runtime = lambda source, digest: calls.append(
        ("verify", source, digest)
    )
    fake.run = lambda argv, timeout=30: calls.append(("run", tuple(argv))) or SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    fake.require_unit = lambda unit, **expected: (
        {"SubState": "waiting"} if unit == fake.TARGET_TIMER else {}
    )
    fake.require_no_job = lambda unit, values: calls.append(("no-job", unit))

    with patch.object(resume, "preflight", return_value=fake):
        resume.apply_resume("a" * 40, "b" * 40, "sha256:" + "c" * 64)

    assert resume.MUTATION_STARTED is True
    assert calls[0][0] == "reconcile"
    assert calls[1][0] == "verify"
    enable = (
        "run",
        ("/usr/bin/systemctl", "enable", "--now", fake.TARGET_TIMER),
    )
    assert enable in calls
    assert calls.count(("verify", "b" * 40, "sha256:" + "c" * 64)) == 2


def test_resume_source_has_no_legacy_restart_cleanup_or_compose_materialization():
    source = RESUME_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "materialize_compose",
        '"disable", "--now", cutover.LEGACY',
        '"enable", "--now", cutover.LEGACY',
        "os.unlink(",
        "shutil.rmtree",
        "docker rm",
        "docker stop",
        "rollback",
    ):
        assert forbidden not in source.lower() if forbidden.islower() else forbidden not in source
    assert '("/usr/bin/systemctl", "enable", "--now", cutover.TARGET_TIMER)' in source
    assert 'STATUS_SHA256 = "42187d0258d92b4dfb644d8d2261a4dc604d77b81d542eb93d3637c5e681cf5d"' in source


def test_resume_contract_pins_partial_state_and_helper_recovery():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["schema"] == "rozkalns.rpi5-main.hermes-tech-simple-deploy-resume.v1"
    assert contract["issue"] == 1451
    assert contract["operation_id"] == "rpi5-main.hermes-tech-simple-deploy-resume.v1"
    assert contract["execution_enabled"] is False
    assert contract["authorization_class"] == "STRICT"
    assert contract["one_time"] is True

    root = contract["root_cause"]
    assert root["failure_type"] == "TypeError"
    assert root["failure_reason"] == "pinned-generic-inspect-api-does-not-accept-origin-keyword"
    assert root["failure_before_generic_status_write"] is True
    assert root["pinned_generic_module_sha256"] == (
        "ed906786fd85169c6c555a3ac466b157edaf24a65fe12f60ee2ec6940ade20d0"
    )

    recovery = contract["helper_recovery"]
    assert recovery["baseline_main"] == "1af1b450a0082894f405343505b6fb07606a26c1"
    assert recovery["required_initial_sha256"] == (
        "8a6cb72706c61dffd1c126c825169f92363edcbf328fb0bce42bdf60a014d050"
    )
    assert recovery["target_path"] == (
        "/usr/local/libexec/rozkalns-simple-deployer/hermes-tech-exact-reconcile-v1"
    )
    assert recovery["atomic_replace_once"] is True
    assert recovery["automatic_retry"] is False
    assert recovery["automatic_cleanup"] is False
    assert recovery["automatic_rollback"] is False

    baseline = contract["partial_baseline"]
    assert baseline["compose_sha256"] == (
        "fd1ca0d00c79bfb5e5cd1be589ae13b378c5c223be0b61d3f14f31da687fe6b9"
    )
    assert baseline["stale_status_sha256"] == (
        "42187d0258d92b4dfb644d8d2261a4dc604d77b81d542eb93d3637c5e681cf5d"
    )
    assert baseline["loopback_required_unbound"] is True
    assert baseline["receipt_required_absent"] is True
    assert baseline["legacy_container_required_absent"] is True
    assert baseline["simple_deploy_container_required_absent"] is True


def test_resume_registry_operation_is_strict_and_forward_only():
    registry = json.loads(EXECUTOR_REGISTRY_PATH.read_text(encoding="utf-8"))
    operation = next(
        item
        for item in registry["operations"]
        if item["operation_id"] == "rpi5-main.hermes-tech-simple-deploy-resume.v1"
    )

    assert registry["execution_enabled"] is False
    assert operation["authorization_class"] == "STRICT"
    assert operation["ordinary_live_all_eligible"] is False
    assert operation["rollback_policy"] == "NONE"
    assert operation["queue_match"] == {
        "target_alias": "hermes-tech-public-rpi5",
        "execution_location_class": "trusted-home-host",
        "repository_entrypoint": "ops/bin/hermes-tech-simple-deploy-resume-v1",
        "deploy_class": "STRICT_LIVE_AUTH_REQUIRED",
    }
    assert {
        item["category"]: item["max_operations"]
        for item in operation["mutation_budget"]
    } == {
        "filesystem.hermes-tech-exact-helper-recovery": 1,
        "filesystem.hermes-tech-resume-operator-installation": 1,
        "docker.hermes-tech-simple-deploy-application-apply": 1,
        "systemd.hermes-tech-target-timer-activation": 1,
    }
    exclusions = "\n".join(operation["exclusions"]).lower()
    assert "legacy hermes tech runtime restart or rollback" in exclusions
    assert "global simple-deploy all-target timer activation" in exclusions
    assert "automatic retry cleanup rollback" in exclusions
