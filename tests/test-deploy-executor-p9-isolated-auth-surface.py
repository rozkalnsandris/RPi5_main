#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import p9_isolated_auth_surface as isolated

CONTRACT_PATH = ROOT / "ops" / "deploy" / "executor-p9-isolated-auth-surface.json"


def load_raw() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def expect_error(payload: dict, contains: str) -> None:
    try:
        isolated.validate_contract(payload)
    except isolated.IsolatedAuthSurfaceError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected IsolatedAuthSurfaceError containing {contains!r}")


def test_repository_contract_is_dormant_and_unbound() -> None:
    contract = isolated.load_contract(CONTRACT_PATH)
    assert contract.authorization_repository == "rozkalnsandris/deploy-authorizations"
    assert contract.authorization_repository_id is None
    assert contract.observed_repository_id == 1350486101
    assert contract.queue_repository == "rozkalnsandris/ops-workflows"
    assert contract.queue_repository_id == 1328835922
    assert contract.owner_user_id == 277435981
    assert contract.activation_enabled is False
    assert contract.runtime_binding_ready is False
    assert contract.host_wiring_enabled is False
    assert contract.production_mutation_enabled is False


def test_actions_must_be_disabled_and_issues_enabled() -> None:
    payload = load_raw()
    payload["actions_enabled"] = True
    expect_error(payload, "actions_enabled must be false")
    payload = load_raw()
    payload["issues_enabled"] = False
    expect_error(payload, "issues_enabled must be true")


def test_isolated_repository_must_be_private() -> None:
    payload = load_raw()
    payload["authorization_repository_visibility"] = "public"
    expect_error(payload, "must be private")


def test_queue_repository_remains_ops_workflows() -> None:
    payload = load_raw()
    payload["queue_repository"] = "rozkalnsandris/deploy-authorizations"
    expect_error(payload, "queue repository drifted")
    payload = load_raw()
    payload["queue_repository_id"] += 1
    expect_error(payload, "queue repository id drifted")


def test_owner_is_the_only_authorization_writer() -> None:
    payload = load_raw()
    payload["authorization_writer"]["required_actor_type"] = "Bot"
    expect_error(payload, "actor type must be User")
    payload = load_raw()
    payload["authorization_writer"]["app_authored_issues_allowed"] = True
    expect_error(payload, "app_authored_issues_allowed must be false")
    payload = load_raw()
    payload["approved_operator_integrations"].append({"app_id": 1144995})
    expect_error(payload, "approved operator integrations must remain empty")


def test_broad_connector_is_explicitly_excluded() -> None:
    payload = load_raw()
    payload["excluded_operator_integrations"][0]["app_id"] += 1
    expect_error(payload, "excluded operator app id drifted")
    payload = load_raw()
    payload["excluded_operator_integrations"][0]["observed_repository_permissions"][
        "contents"
    ] = "read"
    expect_error(payload, "excluded operator permission evidence drifted")
    payload = load_raw()
    payload["excluded_operator_integrations"] = []
    expect_error(payload, "exactly one excluded operator integration")


def test_partial_setup_evidence_is_exact_and_non_authorizing() -> None:
    payload = load_raw()
    payload["observed_repository_setup"]["repository_id"] += 1
    expect_error(payload, "observed authorization repository id drifted")
    payload = load_raw()
    payload["observed_repository_setup"]["installed_github_app_count"] = 1
    expect_error(payload, "zero installed GitHub Apps")
    payload = load_raw()
    payload["observed_repository_setup"]["status"] = "accepted"
    expect_error(payload, "observed setup status drifted")


def test_executor_remains_read_only() -> None:
    payload = load_raw()
    payload["executor_app"]["issues_permission"] = "write"
    expect_error(payload, "Issues read + Metadata read")
    payload = load_raw()
    payload["executor_app"]["write_permissions_allowed"] = True
    expect_error(payload, "write_permissions_allowed must be false")


def test_every_repository_invariant_must_remain_true() -> None:
    for key in load_raw()["required_repository_invariants"]:
        payload = load_raw()
        payload["required_repository_invariants"][key] = False
        expect_error(payload, f"required_repository_invariants.{key} must be true")


def test_unbound_repository_id_forbids_activation() -> None:
    for key in (
        "activation_enabled",
        "runtime_binding_ready",
        "host_wiring_enabled",
        "production_mutation_enabled",
    ):
        payload = load_raw()
        payload[key] = True
        expect_error(payload, "unbound authorization repository id requires dormant fail-closed state")


def test_bound_id_alone_does_not_enable_runtime() -> None:
    payload = load_raw()
    payload["authorization_repository_id"] = 1350486101
    contract = isolated.validate_contract(payload)
    assert contract.authorization_repository_id == 1350486101
    assert contract.activation_enabled is False
    assert contract.runtime_binding_ready is False


def test_activation_requires_runtime_binding() -> None:
    payload = load_raw()
    payload["authorization_repository_id"] = 1350486101
    payload["activation_enabled"] = True
    expect_error(payload, "activation requires runtime_binding_ready")


def test_host_wiring_requires_activation() -> None:
    payload = load_raw()
    payload["authorization_repository_id"] = 1350486101
    payload["runtime_binding_ready"] = True
    payload["host_wiring_enabled"] = True
    expect_error(payload, "host wiring requires activation")


def test_p9_contract_can_never_enable_production_mutation() -> None:
    payload = load_raw()
    payload["authorization_repository_id"] = 1350486101
    payload["runtime_binding_ready"] = True
    payload["activation_enabled"] = True
    payload["host_wiring_enabled"] = True
    payload["production_mutation_enabled"] = True
    expect_error(payload, "may not enable production mutation")


def test_unknown_or_missing_keys_fail_closed() -> None:
    payload = load_raw()
    payload["unexpected"] = True
    expect_error(payload, "contract keys mismatch")
    payload = load_raw()
    del payload["actions_enabled"]
    expect_error(payload, "contract keys mismatch")


def test_loader_rejects_malformed_json() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "contract.json"
        path.write_text("{broken", encoding="utf-8")
        try:
            isolated.load_contract(path)
        except isolated.IsolatedAuthSurfaceError as exc:
            assert "unreadable" in str(exc)
        else:
            raise AssertionError("expected malformed JSON rejection")


def main() -> None:
    tests = [
        value
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    for test in sorted(tests, key=lambda fn: fn.__name__):
        test()
    print(f"P9_ISOLATED_AUTH_SURFACE_TESTS=PASS count={len(tests)}")


if __name__ == "__main__":
    main()
