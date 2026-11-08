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
        'TARGET_TIMER = "rozkalns-simple-deployer@hermes-tech-public-rpi5.timer"',
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
    assert "os.O_EXCL" in source
    assert "os.replace" not in source
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
