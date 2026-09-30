import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/deploy/hermes-tech-simple-deploy-cutover-v1.json"
EXECUTOR_REGISTRY_PATH = ROOT / "ops/deploy/executor-operations.json"
TARGET_REGISTRY_PATH = ROOT / "ops/deploy/simple-deploy-targets-v1.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _by(items, key, value):
    return next(item for item in items if item[key] == value)


def test_cutover_contract_is_source_only_strict_and_fail_closed():
    contract = _load(CONTRACT_PATH)

    assert contract["schema"] == "rozkalns.rpi5-main.hermes-tech-simple-deploy-cutover.v1"
    assert contract["operation_id"] == "rpi5-main.hermes-tech-simple-deploy-cutover.v1"
    assert contract["execution_enabled"] is False
    assert contract["target_alias"] == "hermes-tech-public-rpi5"
    assert contract["authorization_class"] == "STRICT"
    assert contract["one_time"] is True
    assert contract["source_only_state"] == {
        "live_authorized": False,
        "runtime_mutation_permitted_by_this_file": False,
        "merge_authorized": False,
    }
    assert contract["failure_semantics"] == {
        "fail_closed": True,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "alternate_mutation_path": False,
        "preserve_evidence": True,
        "stop_after_first_post_mutation_error_or_ambiguity": True,
    }


def test_cutover_contract_pins_legacy_runtime_materialization_and_port_transition():
    contract = _load(CONTRACT_PATH)

    assert contract["legacy_runtime"]["web_unit"]["name"] == "hermes-tech-web.service"
    assert contract["legacy_runtime"]["pull_timer_unit"]["name"] == "hermes-tech-pull-deploy.timer"
    assert contract["legacy_runtime"]["pull_service_unit"]["name"] == "hermes-tech-pull-deploy.service"

    materialization = contract["target_materialization"]
    assert materialization["source_path"] == "ops/deploy/simple-deploy-compose/hermes-tech-public.yml"
    assert materialization["source_sha256"] == "fd1ca0d00c79bfb5e5cd1be589ae13b378c5c223be0b61d3f14f31da687fe6b9"
    assert materialization["destination_path"] == "/etc/rozkalns-simple-deployer/compose/hermes-tech-public.yml"
    assert materialization["required_initial_destination_state"] == "absent"

    transition = contract["port_ownership_transition"]
    assert transition == {
        "bind": "127.0.0.1:8089",
        "required_before_owner": "hermes-tech-web.service",
        "required_between_state": "unbound",
        "required_after_owner": "compose:hermes-tech-public/hermes-tech",
        "parallel_bind_forbidden": True,
    }

    verification = contract["verification"]
    assert verification["liveness_url"] == "http://127.0.0.1:8089/health"
    assert verification["readiness_url"] == "http://127.0.0.1:8089/ready"
    assert verification["required_http_status"] == 200
    assert verification["receipt_path"] == "/var/lib/rozkalns-simple-deployer/receipts/hermes-tech-public-rpi5.json"


def test_cutover_contract_matches_simple_deploy_target_registry():
    contract = _load(CONTRACT_PATH)
    target_registry = _load(TARGET_REGISTRY_PATH)
    target = _by(target_registry["targets"], "target_alias", "hermes-tech-public-rpi5")

    assert target["consumer_repository"] == "rozkalnsandris/hermes-tech"
    assert target["image"] == contract["source_contract"]["image"]
    assert target["compose"]["project"] == contract["source_contract"]["compose_project"]
    assert target["compose"]["service"] == contract["source_contract"]["compose_service"]
    assert target["compose"]["file_sha256"] == contract["source_contract"]["compose_source_sha256"]
    assert target["health"]["liveness_url"] == contract["verification"]["liveness_url"]
    assert target["health"]["readiness_url"] == contract["verification"]["readiness_url"]
    assert target["persistent_volumes"] == []


def test_executor_registry_keeps_cutover_strict_and_globally_disabled():
    registry = _load(EXECUTOR_REGISTRY_PATH)
    operation = _by(registry["operations"], "operation_id", "rpi5-main.hermes-tech-simple-deploy-cutover.v1")

    assert registry["execution_enabled"] is False
    assert operation["source_repository"] == "rozkalnsandris/RPi5_main"
    assert operation["target_alias"] == "hermes-tech-public-rpi5"
    assert operation["queue_match"] == {
        "target_alias": "hermes-tech-public-rpi5",
        "execution_location_class": "trusted-home-host",
        "repository_entrypoint": "ops/deploy/hermes-tech-simple-deploy-cutover-v1.json",
        "deploy_class": "STRICT_LIVE_AUTH_REQUIRED",
    }
    assert operation["adapter_id"] == "rpi5-main.hermes-tech-simple-deploy-cutover.v1"
    assert operation["authorization_class"] == "STRICT"
    assert operation["ordinary_live_all_eligible"] is False
    assert operation["rollback_policy"] == "NONE"


def test_cutover_order_prevents_parallel_8089_ownership():
    contract = _load(CONTRACT_PATH)
    steps = contract["ordered_steps"]

    web_stop = steps.index("stop-and-disable-hermes-tech-web.service")
    unbound = steps.index("verify-127.0.0.1:8089-is-unbound")
    materialize = steps.index("materialize-exact-hermes-tech-public-compose")
    deploy = steps.index(
        "apply-hermes-tech-public-rpi5-through-reviewed-generic-simple-deploy-with-exact-image-digest"
    )
    health = steps.index("verify-health-200")
    ready = steps.index("verify-ready-200")

    assert web_stop < unbound < materialize < deploy < health < ready
    assert contract["port_ownership_transition"]["parallel_bind_forbidden"] is True
    assert contract["generic_simple_deploy_apply"]["exact_image_digest_required"] is True
    assert "generic-shell-or-arbitrary-command-execution" in contract["forbidden_operations"]
