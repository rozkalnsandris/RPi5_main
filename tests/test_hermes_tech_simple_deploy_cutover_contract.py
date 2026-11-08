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
    assert contract["issue"] == 1447
    assert contract["operation_id"] == "rpi5-main.hermes-tech-simple-deploy-cutover.v1"
    assert contract["execution_enabled"] is False
    assert contract["target_alias"] == "hermes-tech-public-rpi5"
    assert contract["authorization_class"] == "STRICT"
    assert contract["one_time"] is True
    assert contract["source_only_state"] == {
        "live_authorized": False,
        "runtime_mutation_permitted_by_this_file": False,
        "merge_authorized": False,
        "operator_installation_authorized": False,
        "target_timer_activation_authorized": False,
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


def test_cutover_contract_pins_operator_closure_and_exact_release_adapter():
    contract = _load(CONTRACT_PATH)
    install = contract["operator_installation"]
    assert install == {
        "installer_source": "ops/bin/install-hermes-tech-simple-deploy-cutover-v1",
        "entrypoint_source": "ops/bin/hermes-tech-simple-deploy-cutover-v1",
        "support_source": "ops/bin/hermes-tech-exact-reconcile-v1",
        "installed_entrypoint": "/usr/local/sbin/hermes-tech-simple-deploy-cutover-v1",
        "installed_support": "/usr/local/libexec/rozkalns-simple-deployer/hermes-tech-exact-reconcile-v1",
        "required_initial_state": "both-absent",
        "publication_order": ["support", "entrypoint"],
        "entrypoint_owner": "root",
        "entrypoint_group": "root",
        "entrypoint_mode": "0500",
        "support_owner": "root",
        "support_group": "root",
        "support_mode": "0555",
        "partial_support_without_entrypoint_is_inert": True,
        "separate_live_installation_authorization_required": True,
        "source_merge_installs_operator": False,
    }

    adapter = contract["exact_release_adapter"]
    assert adapter["generic_deployer_module"] == "/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_v1.py"
    assert adapter["compatible_deployer_identity_source_sha"] == "62fd973653754fb489bda5c7d803015def71a6f4"
    assert adapter["compatible_deployer_module_sha256"] == "ed906786fd85169c6c555a3ac466b157edaf24a65fe12f60ee2ec6940ade20d0"
    assert adapter["runtime_user"] == "rozkalns-simple-deployer"
    assert adapter["caller_release_inputs"] == ["expected-source-sha", "expected-image-digest"]
    assert adapter["caller_path_command_environment_inputs_forbidden"] is True
    assert adapter["production_pointer_must_equal_expected_digest_before_mutation"] is True
    assert adapter["image_label_source_must_equal_expected_source_before_mutation"] is True
    assert adapter["production_pointer_must_remain_expected_digest_after_mutation"] is True
    assert adapter["reuses_generic_simple_deploy_state_machine"] is True
    assert adapter["modifies_generic_simple_deploy_source"] is False


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


def test_cutover_contract_activates_only_target_scoped_timer():
    contract = _load(CONTRACT_PATH)
    standing = contract["standing_reconciliation"]
    assert standing["target_timer"] == "rozkalns-simple-deployer@hermes-tech-public-rpi5.timer"
    assert standing["target_service"] == "rozkalns-simple-deployer@hermes-tech-public-rpi5.service"
    assert standing["required_initial_timer_enabled_state"] == "disabled"
    assert standing["required_initial_timer_active_state"] == "inactive"
    assert standing["final_timer_enabled_state"] == "enabled"
    assert standing["final_timer_active_state"] == "active"
    assert standing["global_timer"] == "rozkalns-simple-deployer.timer"
    assert standing["global_timer_required_enabled_state"] == "disabled"
    assert standing["global_timer_required_active_state"] == "inactive"
    assert standing["global_all_target_reconciliation_forbidden"] is True
    assert "global-simple-deployer-all-target-timer-enable-or-start" in contract["forbidden_operations"]


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


def test_executor_registry_keeps_cutover_strict_and_binds_fixed_operator():
    registry = _load(EXECUTOR_REGISTRY_PATH)
    operation = _by(registry["operations"], "operation_id", "rpi5-main.hermes-tech-simple-deploy-cutover.v1")

    assert registry["execution_enabled"] is False
    assert operation["source_repository"] == "rozkalnsandris/RPi5_main"
    assert operation["target_alias"] == "hermes-tech-public-rpi5"
    assert operation["queue_match"] == {
        "target_alias": "hermes-tech-public-rpi5",
        "execution_location_class": "trusted-home-host",
        "repository_entrypoint": "ops/bin/hermes-tech-simple-deploy-cutover-v1",
        "deploy_class": "STRICT_LIVE_AUTH_REQUIRED",
    }
    assert operation["adapter_id"] == "rpi5-main.hermes-tech-simple-deploy-cutover.v1"
    assert operation["authorization_class"] == "STRICT"
    assert operation["ordinary_live_all_eligible"] is False
    assert operation["rollback_policy"] == "NONE"
    categories = {item["category"]: item["max_operations"] for item in operation["mutation_budget"]}
    assert categories == {
        "filesystem.hermes-tech-cutover-operator-installation": 2,
        "systemd.hermes-tech-legacy-runtime-retirement": 3,
        "filesystem.hermes-tech-simple-deploy-materialization": 1,
        "docker.hermes-tech-simple-deploy-application-apply": 1,
        "systemd.hermes-tech-target-timer-activation": 1,
    }


def test_cutover_order_prevents_parallel_8089_ownership_and_global_timer_activation():
    contract = _load(CONTRACT_PATH)
    steps = contract["ordered_steps"]

    release = steps.index("revalidate-authorized-hermes-tech-source-and-immutable-digest")
    web_stop = steps.index("stop-and-disable-hermes-tech-web.service")
    unbound = steps.index("verify-hermes-blog-is-absent-and-127.0.0.1:8089-is-unbound")
    materialize = steps.index("materialize-exact-hermes-tech-public-compose")
    deploy = steps.index("apply-hermes-tech-public-rpi5-through-fixed-exact-release-helper")
    health = steps.index("verify-health-200")
    ready = steps.index("verify-ready-200")
    receipt = steps.index("verify-simple-deploy-receipt-exact-source-and-digest")
    timer = steps.index("enable-and-start-hermes-tech-target-scoped-simple-deploy-timer")

    assert release < web_stop < unbound < materialize < deploy < health < ready < receipt < timer
    assert contract["port_ownership_transition"]["parallel_bind_forbidden"] is True
    assert contract["generic_simple_deploy_apply"]["exact_image_digest_required"] is True
    assert "generic-shell-or-arbitrary-command-execution" in contract["forbidden_operations"]
