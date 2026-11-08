from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR_PATH = ROOT / "ops/bin/hermes-tech-simple-deploy-cutover-v1"
INSTALLER_PATH = ROOT / "ops/bin/install-hermes-tech-simple-deploy-cutover-v1"
HELPER_PATH = ROOT / "ops/bin/hermes-tech-exact-reconcile-v1"
GENERIC_DEPLOYER_PATH = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"


def _load(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


operator = _load("hermes_cutover_operator_test", OPERATOR_PATH)
installer = _load("hermes_cutover_installer_test", INSTALLER_PATH)


def test_new_python_sources_parse_and_use_isolated_python():
    for path in (OPERATOR_PATH, INSTALLER_PATH, HELPER_PATH):
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
        assert source.startswith("#!/usr/bin/python3 -I\n")


def test_exact_release_helper_has_only_release_identity_authority():
    source = HELPER_PATH.read_text(encoding="utf-8")
    assert 'parser.add_argument("--expected-source", required=True)' in source
    assert 'parser.add_argument("--expected-digest", required=True)' in source
    assert "sd._production_deployer()" in source
    assert "class ExactReleaseDeployer(sd.SimpleDeployer)" in source
    assert "EXPECTED_DIGEST_MISMATCH" in source
    assert "EXPECTED_SOURCE_MISMATCH" in source
    assert "COMPATIBLE_DEPLOYER_SHA256" in source

    for forbidden in (
        'add_argument("--path"',
        'add_argument("--command"',
        'add_argument("--environment"',
        "shell=True",
        "os.system(",
        "systemctl",
        '"docker", "compose"',
    ):
        assert forbidden not in source


def test_cutover_operator_is_fixed_scope_and_target_timer_only():
    source = OPERATOR_PATH.read_text(encoding="utf-8")
    for required in (
        'LEGACY_WEB_UNIT = "hermes-tech-web.service"',
        'LEGACY_PULL_TIMER = "hermes-tech-pull-deploy.timer"',
        'LEGACY_PULL_SERVICE = "hermes-tech-pull-deploy.service"',
        'LEGACY_CONTAINER = "hermes-blog"',
        'TARGET_TIMER_INSTANCE = "hermes-tech-public-rpi5"',
        'TARGET_TIMER = f"rozkalns-simple-deployer{chr(64)}{TARGET_TIMER_INSTANCE}.timer"',
        'GLOBAL_TIMER = "rozkalns-simple-deployer.timer"',
        'TARGET_ALIAS = "hermes-tech-public-rpi5"',
        'RUNTIME_USER = "rozkalns-simple-deployer"',
        '"/usr/sbin/runuser", "-u", RUNTIME_USER',
        'EXPECTED_COMPOSE_SHA256 = "fd1ca0d00c79bfb5e5cd1be589ae13b378c5c223be0b61d3f14f31da687fe6b9"',
    ):
        assert required in source

    for forbidden in (
        "shell=True",
        "os.system(",
        "eval(",
        "exec(",
        "docker inspect",
        "cloudflared",
        "ufw",
        "postgres",
        "sqlite",
        "database",
        '"/usr/bin/systemctl", "enable", "--now", GLOBAL_TIMER',
        'add_argument("--path"',
        'add_argument("--command"',
        'add_argument("--environment"',
    ):
        assert forbidden not in source.lower() if forbidden.islower() else forbidden not in source


def test_installer_is_two_fixed_files_support_first_and_no_cleanup():
    source = INSTALLER_PATH.read_text(encoding="utf-8")
    assert 'HELPER_DEST = Path("/usr/local/libexec/rozkalns-simple-deployer/hermes-tech-exact-reconcile-v1")' in source
    assert 'OPERATOR_DEST = Path("/usr/local/sbin/hermes-tech-simple-deploy-cutover-v1")' in source
    assert "install_once(HELPER_DEST, helper, 0o555)" in source
    assert "install_once(OPERATOR_DEST, operator, 0o500)" in source
    assert source.index("install_once(HELPER_DEST") < source.index("install_once(OPERATOR_DEST")
    assert 'if Path(__file__).absolute() != expected_installer:' in source
    assert "os.O_EXCL" in source
    assert "OPERATOR_UPGRADE_STAGE" in source
    assert "os.replace(OPERATOR_UPGRADE_STAGE, OPERATOR_DEST)" in source
    assert "unlink(" not in source
    assert "remove(" not in source
    assert "rmtree(" not in source
    assert "shell=True" not in source
    for forbidden in (
        'add_argument("--path"',
        'add_argument("--destination"',
        'add_argument("--command"',
        'add_argument("--environment"',
    ):
        assert forbidden not in source


def test_timer_status_may_omit_mainpid_and_normalizes_to_zero():
    observed = """LoadState=loaded
ActiveState=active
SubState=running
UnitFileState=enabled
Job=
NeedDaemonReload=no
"""
    with patch.object(
        operator,
        "run",
        return_value=SimpleNamespace(returncode=0, stdout=observed, stderr=""),
    ):
        values = operator.unit_properties(operator.LEGACY_PULL_TIMER)

    assert values == {
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "running",
        "UnitFileState": "enabled",
        "Job": "0",
        "NeedDaemonReload": "no",
        "MainPID": "0",
    }


def test_service_status_still_requires_mainpid():
    observed = """LoadState=loaded
ActiveState=inactive
SubState=dead
UnitFileState=static
Job=
NeedDaemonReload=no
"""
    with patch.object(
        operator,
        "run",
        return_value=SimpleNamespace(returncode=0, stdout=observed, stderr=""),
    ):
        with pytest.raises(
            operator.CutoverError,
            match=r"^systemd_status_invalid:hermes-tech-pull-deploy\.service$",
        ):
            operator.unit_properties(operator.LEGACY_PULL_SERVICE)


def test_apply_cutover_uses_reviewed_order_and_never_starts_global_timer():
    operator.MUTATION_STARTED = False
    calls: list[tuple[str, ...]] = []

    def fake_run(argv, *, timeout=30, ok=(0,)):
        call = tuple(argv)
        calls.append(call)
        if call[:3] == ("/usr/bin/docker", "ps", "-a"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_require_unit(unit, **expected):
        if unit == operator.TARGET_TIMER:
            return {"SubState": "waiting"}
        return {}

    with (
        patch.object(operator, "preflight", return_value=(b"compose-bytes", object())),
        patch.object(operator, "run", side_effect=fake_run),
        patch.object(operator, "require_unit", side_effect=fake_require_unit),
        patch.object(operator, "require_no_job", return_value=None),
        patch.object(operator, "require_port_unbound", return_value=None),
        patch.object(operator, "materialize_compose") as materialize,
        patch.object(operator, "invoke_exact_reconcile") as reconcile,
        patch.object(operator, "verify_new_runtime") as verify,
    ):
        operator.apply_cutover("a" * 40, "b" * 40, "sha256:" + "c" * 64)

    assert operator.MUTATION_STARTED is True
    assert calls[0] == (
        "/usr/bin/systemctl",
        "disable",
        "--now",
        operator.LEGACY_PULL_TIMER,
    )
    assert calls[1] == (
        "/usr/bin/systemctl",
        "stop",
        operator.LEGACY_PULL_SERVICE,
    )
    assert calls[2] == (
        "/usr/bin/systemctl",
        "disable",
        "--now",
        operator.LEGACY_WEB_UNIT,
    )
    assert calls[-1] == (
        "/usr/bin/systemctl",
        "enable",
        "--now",
        operator.TARGET_TIMER,
    )
    assert not any(
        call == (
            "/usr/bin/systemctl",
            "enable",
            "--now",
            operator.GLOBAL_TIMER,
        )
        for call in calls
    )
    materialize.assert_called_once_with(b"compose-bytes")
    reconcile.assert_called_once_with("b" * 40, "sha256:" + "c" * 64)
    assert verify.call_count == 2


def test_first_apply_failure_is_already_post_mutation():
    operator.MUTATION_STARTED = False
    with (
        patch.object(operator, "preflight", return_value=(b"compose", object())),
        patch.object(operator, "run", side_effect=operator.CutoverError("synthetic")),
    ):
        with pytest.raises(operator.CutoverError):
            operator.apply_cutover("a" * 40, "b" * 40, "sha256:" + "c" * 64)
    assert operator.MUTATION_STARTED is True


def test_installer_apply_publishes_support_before_root_entrypoint():
    installer.MUTATION_STARTED = False
    order = []

    def fake_install(path, data, mode):
        order.append((path, data, mode))

    out = io.StringIO()
    with (
        patch.object(installer, "source_closure", return_value=(b"helper", b"operator")),
        patch.object(installer, "install_once", side_effect=fake_install),
        redirect_stdout(out),
    ):
        rc = installer.main([
            "apply",
            "--expected-main",
            "a" * 40,
            "--confirm",
            "INSTALL-HERMES-TECH-CUTOVER-CLOSURE",
        ])

    assert rc == 0
    assert order == [
        (installer.HELPER_DEST, b"helper", 0o555),
        (installer.OPERATOR_DEST, b"operator", 0o500),
    ]


def test_operator_upgrade_check_is_read_only():
    installer.MUTATION_STARTED = False
    desired = b"reviewed-new-operator"
    out = io.StringIO()
    with (
        patch.object(
            installer,
            "operator_upgrade_preflight",
            return_value=(desired, (1, 2, 3, 4), (5, 6, 7, 8)),
        ),
        patch.object(installer, "upgrade_operator_once") as upgrade,
        redirect_stdout(out),
    ):
        rc = installer.main([
            "upgrade-check",
            "--expected-main",
            "a" * 40,
        ])

    assert rc == 0
    upgrade.assert_not_called()
    payload = __import__("json").loads(out.getvalue())
    assert payload["result"] == "READY"
    assert payload["mutation_started"] is False
    assert payload["baseline_main"] == installer.UPGRADE_BASELINE_MAIN


def test_operator_upgrade_atomically_replaces_only_operator(tmp_path):
    installer.MUTATION_STARTED = False
    operator_dest = tmp_path / "hermes-tech-simple-deploy-cutover-v1"
    helper_dest = tmp_path / "hermes-tech-exact-reconcile-v1"
    stage = tmp_path / ".hermes-tech-simple-deploy-cutover-v1.issue1449.stage"
    operator_dest.write_bytes(b"old-operator")
    helper_dest.write_bytes(b"helper")
    desired = b"new-operator"
    old_identity = (1, 10, 100, len(b"old-operator"))
    helper_identity = (1, 20, 200, len(b"helper"))

    def fake_read(path, *, mode):
        data = path.read_bytes()
        inode = 30 if path == stage else 40 if path == operator_dest else 20
        return (1, inode, 300, len(data)), data

    with (
        patch.object(installer, "OPERATOR_DEST", operator_dest),
        patch.object(installer, "HELPER_DEST", helper_dest),
        patch.object(installer, "OPERATOR_UPGRADE_STAGE", stage),
        patch.object(
            installer,
            "operator_upgrade_preflight",
            return_value=(desired, old_identity, helper_identity),
        ),
        patch.object(
            installer,
            "operator_upgrade_preflight_without_stage",
            return_value=(desired, old_identity, helper_identity),
        ),
        patch.object(
            installer,
            "source_context",
            return_value=(tmp_path, b"helper", desired),
        ),
        patch.object(installer, "read_installed", side_effect=fake_read),
        patch.object(installer.os, "fchown", return_value=None),
    ):
        assert installer.upgrade_operator_once("a" * 40) == "PASS"

    assert installer.MUTATION_STARTED is True
    assert operator_dest.read_bytes() == desired
    assert helper_dest.read_bytes() == b"helper"
    assert not stage.exists()


def test_operator_upgrade_replace_error_preserves_stage_and_baseline(tmp_path):
    installer.MUTATION_STARTED = False
    operator_dest = tmp_path / "hermes-tech-simple-deploy-cutover-v1"
    helper_dest = tmp_path / "hermes-tech-exact-reconcile-v1"
    stage = tmp_path / ".hermes-tech-simple-deploy-cutover-v1.issue1449.stage"
    operator_dest.write_bytes(b"old-operator")
    helper_dest.write_bytes(b"helper")
    desired = b"new-operator"
    old_identity = (1, 10, 100, len(b"old-operator"))
    helper_identity = (1, 20, 200, len(b"helper"))

    def fake_read(path, *, mode):
        data = path.read_bytes()
        inode = 30 if path == stage else 40 if path == operator_dest else 20
        return (1, inode, 300, len(data)), data

    with (
        patch.object(installer, "OPERATOR_DEST", operator_dest),
        patch.object(installer, "HELPER_DEST", helper_dest),
        patch.object(installer, "OPERATOR_UPGRADE_STAGE", stage),
        patch.object(
            installer,
            "operator_upgrade_preflight",
            return_value=(desired, old_identity, helper_identity),
        ),
        patch.object(
            installer,
            "operator_upgrade_preflight_without_stage",
            return_value=(desired, old_identity, helper_identity),
        ),
        patch.object(installer, "read_installed", side_effect=fake_read),
        patch.object(installer.os, "fchown", return_value=None),
        patch.object(installer.os, "replace", side_effect=OSError("synthetic")),
    ):
        with pytest.raises(
            installer.InstallError,
            match=r"^operator_upgrade_replace_failed$",
        ):
            installer.upgrade_operator_once("a" * 40)

    assert installer.MUTATION_STARTED is True
    assert operator_dest.read_bytes() == b"old-operator"
    assert helper_dest.read_bytes() == b"helper"
    assert stage.read_bytes() == desired


def test_generic_simple_deploy_source_is_not_extended_with_cutover_cli():
    source = GENERIC_DEPLOYER_PATH.read_text(encoding="utf-8")
    assert 'group.add_argument("--all"' in source
    assert 'group.add_argument("--target"' in source
    for forbidden in (
        '--expected-source',
        '--expected-digest',
        'hermes-tech-simple-deploy-cutover',
        'CUTOVER-HERMES-TECH',
    ):
        assert forbidden not in source
