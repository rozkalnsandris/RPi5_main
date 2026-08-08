#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_PATH = ROOT / "scripts" / "cloudflare_deals_route.py"
AUTHORIZER_PATH = ROOT / "scripts" / "github_rpi5_61_bridge.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deals-9128-route-cutover.yml"

spec = importlib.util.spec_from_file_location("cloudflare_deals_route", OPERATOR_PATH)
assert spec and spec.loader
operator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = operator
spec.loader.exec_module(operator)


def sample_config(service: str = operator.OLD_SERVICE) -> dict:
    origins = {
        "rozkalns.net": "http://127.0.0.1:8088",
        "tech.rozkalns.net": "http://127.0.0.1:8089",
        "deals.rozkalns.net": service,
        "hermes.rozkalns.net": "http://192.168.0.180:9119",
        "portainer.rozkalns.net": "http://192.168.0.180:9000",
        "grafana.rozkalns.net": "http://192.168.0.180:3030",
        "ha.rozkalns.net": "http://192.168.0.180:8123",
        "adguard.rozkalns.net": "http://192.168.0.180:3080",
        "kuma.rozkalns.net": "http://192.168.0.180:3001",
        "prometheus.rozkalns.net": "http://192.168.0.180:9090",
    }
    ingress = [
        {"hostname": hostname, "service": origin, "originRequest": {}}
        for hostname, origin in origins.items()
    ]
    ingress.append({"service": "http_status:404"})
    return {"ingress": ingress, "originRequest": {"connectTimeout": 30}}


def run_authorizer(body: str, *, issue: int = 61, login: str = "rozkalnsandris", user_id: int = 277435981) -> subprocess.CompletedProcess[str]:
    event = {
        "action": "created",
        "issue": {"number": issue},
        "comment": {
            "id": 123456,
            "body": body,
            "author_association": "OWNER" if login == "rozkalnsandris" else "CONTRIBUTOR",
            "user": {"login": login, "id": user_id},
        },
        "sender": {"login": login, "id": user_id},
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        event_path = Path(temp_dir) / "event.json"
        output_path = Path(temp_dir) / "output.txt"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "GITHUB_REPOSITORY": "rozkalnsandris/RPi5_main",
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_OUTPUT": str(output_path),
            }
        )
        result = subprocess.run(
            [sys.executable, str(AUTHORIZER_PATH)],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        result.github_output = output_path.read_text(encoding="utf-8") if output_path.exists() else ""  # type: ignore[attr-defined]
        return result


def test_syntax_and_static_security_boundaries() -> None:
    subprocess.run([sys.executable, "-m", "py_compile", str(OPERATOR_PATH), str(AUTHORIZER_PATH)], check=True)
    operator_text = OPERATOR_PATH.read_text(encoding="utf-8")
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert operator.HOSTNAME == "deals.rozkalns.net"
    assert operator.OLD_SERVICE == "http://192.168.0.180:9128"
    assert operator.NEW_SERVICE == "http://127.0.0.1:9128"
    assert operator.EXPECTED_HOSTNAMES == {
        "rozkalns.net",
        "tech.rozkalns.net",
        "deals.rozkalns.net",
        "hermes.rozkalns.net",
        "portainer.rozkalns.net",
        "grafana.rozkalns.net",
        "ha.rozkalns.net",
        "adguard.rozkalns.net",
        "kuma.rozkalns.net",
        "prometheus.rozkalns.net",
    }

    assert 'suffix="/configurations"' in operator_text
    assert 'method="PUT"' in operator_text
    assert 'body={"config": config}' in operator_text
    assert "CLOUDFLARE_API_TOKEN" in operator_text
    assert "CLOUDFLARE_ACCOUNT_ID" in operator_text
    assert "CLOUDFLARE_TUNNEL_ID" in operator_text
    assert "Authorization" in operator_text

    for forbidden in (
        "/token",
        "/access/",
        "/dns_records",
        "systemctl",
        "cloudflared ",
        "ufw ",
        "docker ",
        "subprocess",
        "os.system",
        "shell=True",
    ):
        assert forbidden not in operator_text

    assert "issue_comment:" in workflow_text
    assert "persist-credentials: false" in workflow_text
    assert "secrets.CLOUDFLARE_API_TOKEN" in workflow_text
    assert "secrets.CLOUDFLARE_ACCOUNT_ID" in workflow_text
    assert "secrets.CLOUDFLARE_TUNNEL_ID" in workflow_text
    assert "issues: write" in workflow_text
    assert "actions/upload-artifact" not in workflow_text
    assert "self-hosted" not in workflow_text
    assert "sudo " not in workflow_text
    assert "cloudflared " not in workflow_text
    assert "docker " not in workflow_text
    assert "ufw " not in workflow_text


def test_authorizer_accepts_only_exact_owner_commands() -> None:
    for command, operation in {
        "/rpi5-61 check": "check",
        "/rpi5-61 cutover": "cutover",
        "/rpi5-61 verify": "verify-loopback",
    }.items():
        result = run_authorizer(command)
        assert result.returncode == 0, result.stdout
        output = result.github_output  # type: ignore[attr-defined]
        assert f"operation={operation}\n" in output
        assert "issue_number=61\n" in output

    for command in (
        "/rpi5-61 cutover now",
        " /rpi5-61 cutover",
        "/rpi5-61 cutover\n",
        "/rpi5-61 rollback",
        "/hermes-307 apply-dual",
    ):
        assert run_authorizer(command).returncode != 0

    assert run_authorizer("/rpi5-61 cutover", issue=60).returncode != 0
    assert run_authorizer("/rpi5-61 cutover", login="someone-else", user_id=1).returncode != 0


def test_config_validator_is_exact_and_fail_closed() -> None:
    config = sample_config()
    index = operator.validate_configuration(config, operator.OLD_SERVICE)
    assert config["ingress"][index]["hostname"] == operator.HOSTNAME

    wrong_origin = sample_config("http://127.0.0.1:9128")
    try:
        operator.validate_configuration(wrong_origin, operator.OLD_SERVICE)
    except operator.RouteError as exc:
        assert str(exc) == "deals_origin_mismatch"
    else:
        raise AssertionError("wrong current Deals origin was accepted")

    extra = sample_config()
    extra["ingress"].insert(-1, {"hostname": "extra.rozkalns.net", "service": "http://127.0.0.1:9999"})
    try:
        operator.validate_configuration(extra, operator.OLD_SERVICE)
    except operator.RouteError as exc:
        assert str(exc) in {"unexpected_ingress_count", "hostname_set_mismatch"}
    else:
        raise AssertionError("unknown route was accepted")

    no_catchall = sample_config()
    no_catchall["ingress"][-1]["service"] = "http_status:200"
    try:
        operator.validate_configuration(no_catchall, operator.OLD_SERVICE)
    except operator.RouteError as exc:
        assert str(exc) == "catchall_contract_mismatch"
    else:
        raise AssertionError("catch-all drift was accepted")


def test_cutover_changes_only_deals_service() -> None:
    original = sample_config()
    puts: list[dict] = []
    reads = 0

    original_get_tunnel = operator.get_tunnel
    original_get_configuration = operator.get_configuration
    original_put_configuration = operator.put_configuration
    original_verify_access_edge = operator.verify_access_edge
    try:
        operator.get_tunnel = lambda *_args: {"name": operator.TUNNEL_NAME, "config_src": "cloudflare"}

        def fake_get(*_args):
            nonlocal reads
            reads += 1
            if reads <= 2:
                return copy.deepcopy(original), 41
            return copy.deepcopy(puts[-1]), 42

        def fake_put(_account, _tunnel, _token, config):
            puts.append(copy.deepcopy(config))

        operator.get_configuration = fake_get
        operator.put_configuration = fake_put
        operator.verify_access_edge = lambda: None

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator.cutover_mode("a" * 32, "00000000-0000-4000-8000-000000000000", "secret-value-not-printed")

        assert len(puts) == 1
        desired = puts[0]
        target_index = operator.validate_configuration(desired, operator.NEW_SERVICE)
        restored = copy.deepcopy(desired)
        restored["ingress"][target_index]["service"] = operator.OLD_SERVICE
        assert restored == original
        assert "RESULT=PASS" in output.getvalue()
        assert "ONLY_DEALS_SERVICE_CHANGED=true" in output.getvalue()
    finally:
        operator.get_tunnel = original_get_tunnel
        operator.get_configuration = original_get_configuration
        operator.put_configuration = original_put_configuration
        operator.verify_access_edge = original_verify_access_edge


def test_post_write_failure_requests_bounded_rollback() -> None:
    original = sample_config()
    puts: list[dict] = []
    reads = 0
    rollback_calls: list[dict] = []

    saved = (
        operator.get_tunnel,
        operator.get_configuration,
        operator.put_configuration,
        operator.verify_access_edge,
        operator.rollback,
    )
    try:
        operator.get_tunnel = lambda *_args: {"name": operator.TUNNEL_NAME, "config_src": "cloudflare"}

        def fake_get(*_args):
            nonlocal reads
            reads += 1
            if reads <= 2:
                return copy.deepcopy(original), 9
            drifted = sample_config(operator.NEW_SERVICE)
            drifted["originRequest"] = {"connectTimeout": 99}
            return drifted, 10

        operator.get_configuration = fake_get
        operator.put_configuration = lambda _a, _t, _k, config: puts.append(copy.deepcopy(config))
        operator.verify_access_edge = lambda: None

        def fake_rollback(_a, _t, _k, config):
            rollback_calls.append(copy.deepcopy(config))
            return True

        operator.rollback = fake_rollback
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                operator.cutover_mode("a" * 32, "00000000-0000-4000-8000-000000000000", "secret-value-not-printed")
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("post-write drift did not fail")

        assert len(puts) == 1
        assert rollback_calls == [original]
        assert "RESULT=FAILED_ROLLBACK_VERIFIED" in output.getvalue()
        assert "AUTO_ROLLBACK=PASS" in output.getvalue()
    finally:
        (
            operator.get_tunnel,
            operator.get_configuration,
            operator.put_configuration,
            operator.verify_access_edge,
            operator.rollback,
        ) = saved


def main() -> None:
    tests = [
        test_syntax_and_static_security_boundaries,
        test_authorizer_accepts_only_exact_owner_commands,
        test_config_validator_is_exact_and_fail_closed,
        test_cutover_changes_only_deals_service,
        test_post_write_failure_requests_bounded_rollback,
    ]
    for test in tests:
        test()
        print(f"{test.__name__}: PASS")
    print("Deals route cutover tests: PASS")


if __name__ == "__main__":
    main()
