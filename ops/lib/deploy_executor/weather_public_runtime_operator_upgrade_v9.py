from __future__ import annotations

from pathlib import Path
from typing import Any

from deploy_executor import weather_public_runtime_operator_upgrade_v2 as _engine

ISSUE = 601
TRUSTED_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v9-trusted"
TRUSTED_CHECKOUT_DERIVATION = f"RPi5_CHECKOUT_PARENT/{TRUSTED_CHECKOUT_NAME}"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
PREDECESSOR_SHA = "77482a16fb77338d87b92a39ff8c63a5b6ce142d"
MINIMUM_TARGET_ANCESTOR = PREDECESSOR_SHA
TARGET_SOURCE = "ops/lib/deploy_executor/weather_public_runtime_operator.py"
CANONICAL_ENTRYPOINT = Path("/usr/local/sbin/rozkalns-weather-public-runtime-operator")
CANONICAL_SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-public-runtime-operator")
TARGET_FILENAME = "weather_public_runtime_operator.py"
TARGET_OLD_BLOB = "c7f089f4535779e3ef507af4564b3fbadb2bbd2a"
TARGET_NEW_BLOB = "b1ae25b956441d6f86bfff65cdd04110a72da4d6"
TARGET_OLD_SHA256 = "48c8c5fb0cdc005bf0e4fbb05a203297e05d7ef62689ddd0d6d717c13acc0fcb"
TARGET_NEW_SHA256 = "d153db5707b1e37e8a3268fc80e57e75ae7248c5ea9f7ab169357b77849ed1a3"
UPGRADE_CONTRACT_RELATIVE = Path("ops/deploy/weather-public-runtime-operator-upgrade-v9.json")
CHECKOUT_CONTRACT_RELATIVE = Path("ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v9-trusted-checkout-bootstrap.json")
UPGRADE_ENTRYPOINT_RELATIVE = Path("ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v9")
UPGRADE_MODULE_RELATIVE = Path("ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v9.py")
TEMP_NAME = ".weather_public_runtime_operator.py.compatibility-upgrade-v9.tmp"
ROOT_UID = 0
ROOT_GID = 0

WeatherOperatorUpgradeError = _engine.WeatherOperatorUpgradeError


def source_readiness() -> dict[str, Any]:
    return {
        "schema": "rozkalns-weather.public-runtime-operator-upgrade-v9-source.v1",
        "issue": ISSUE,
        "caller_authority": (),
        "trusted_upgrade_checkout": TRUSTED_CHECKOUT_DERIVATION,
        "predecessor_sha": PREDECESSOR_SHA,
        "target_source": TARGET_SOURCE,
        "target_old_sha256": TARGET_OLD_SHA256,
        "target_new_sha256": TARGET_NEW_SHA256,
        "mutation_target_count": 1,
        "runtime_live_authority": False,
        "operator_upgrade_enabled": False,
        "operator_invocation_enabled": False,
        "helper_invocation_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "generic_shell_authority": False,
        "caller_supplied_path_allowed": False,
        "caller_supplied_argv_allowed": False,
        "caller_supplied_environment_allowed": False,
        "caller_supplied_repository_url_allowed": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def _validate_upgrade_contract(value: dict[str, Any]) -> None:
    expected = {
        "schema": "rozkalns-weather.public-runtime-operator-upgrade-v9.v1",
        "repository": "rozkalnsandris/RPi5_main",
        "issue": ISSUE,
        "status": "SOURCE_ONLY_UPGRADE_BRIDGE_INACTIVE",
        "predecessor_sha": PREDECESSOR_SHA,
        "minimum_target_ancestor": MINIMUM_TARGET_ANCESTOR,
        "operator_install_manifest": str(_engine.install.CONTRACT_RELATIVE),
        "trusted_upgrade_checkout_contract": str(CHECKOUT_CONTRACT_RELATIVE),
        "trusted_upgrade_checkout": TRUSTED_CHECKOUT_DERIVATION,
        "target_source": TARGET_SOURCE,
        "target_destination": str(CANONICAL_SUPPORT_ROOT / "deploy_executor" / TARGET_FILENAME),
        "old_blob": TARGET_OLD_BLOB,
        "new_blob": TARGET_NEW_BLOB,
        "old_sha256": TARGET_OLD_SHA256,
        "new_sha256": TARGET_NEW_SHA256,
        "required_owner_uid": ROOT_UID,
        "required_owner_gid": ROOT_GID,
        "required_mode": "0644",
        "mutation_target_count": 1,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise WeatherOperatorUpgradeError(f"operator upgrade contract drifted: {key}")
    if value.get("caller_arguments") != [] or value.get("allowed_changed_artifacts") != [TARGET_SOURCE]:
        raise WeatherOperatorUpgradeError("operator upgrade caller/artifact contract drifted")
    if value.get("replacement") != {
        "temporary_name": TEMP_NAME,
        "same_directory": True,
        "no_follow": True,
        "exclusive_create": True,
        "fsync_before_replace": True,
        "atomic_replace": True,
        "parent_fsync_after_replace": True,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "backup_restore": False,
    }:
        raise WeatherOperatorUpgradeError("operator upgrade replacement contract drifted")
    if value.get("safety") != {
        "source_merge_authorizes_live": False,
        "runtime_live_authority": False,
        "generic_shell_authority": False,
        "caller_selected_path": False,
        "caller_selected_argv": False,
        "caller_selected_environment": False,
        "caller_selected_repository_url": False,
        "trusted_checkout_repair": False,
        "docker_mutation": False,
        "systemd_mutation": False,
        "sqlite_or_corpus_mutation": False,
        "network_or_secret_mutation": False,
    }:
        raise WeatherOperatorUpgradeError("operator upgrade safety contract drifted")


def _derive_checkout() -> Path:
    checkout = Path(__file__).resolve().parents[3]
    expected = checkout / UPGRADE_MODULE_RELATIVE
    if checkout.name != TRUSTED_CHECKOUT_NAME or Path(__file__).resolve() != expected.resolve():
        raise WeatherOperatorUpgradeError("Weather operator upgrade v9 is not in the fixed trusted upgrade checkout")
    return checkout


def _receipt(*, result: str, source_sha: str | None, state: dict[str, bool], reason: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "rozkalns-weather.public-runtime-operator-upgrade-v9-receipt.v1",
        "result": result,
        "source_sha": source_sha,
        "predecessor_sha": PREDECESSOR_SHA,
        "old_sha256": TARGET_OLD_SHA256,
        "new_sha256": TARGET_NEW_SHA256,
        "mutation_started": state["mutation_started"],
        "target_replaced": state["target_replaced"],
        "mutation_target_count": 1,
        "operator_invoked": False,
        "helper_invoked": False,
        "docker_mutation": False,
        "systemd_mutation": False,
        "sqlite_or_corpus_mutation": False,
        "network_or_secret_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
    if reason is not None:
        value["reason"] = reason
    return value


def _configure_engine() -> None:
    bindings = {
        "ISSUE": ISSUE,
        "TRUSTED_CHECKOUT_NAME": TRUSTED_CHECKOUT_NAME,
        "TRUSTED_CHECKOUT_DERIVATION": TRUSTED_CHECKOUT_DERIVATION,
        "REVIEWED_ORIGIN": REVIEWED_ORIGIN,
        "PREDECESSOR_SHA": PREDECESSOR_SHA,
        "MINIMUM_TARGET_ANCESTOR": MINIMUM_TARGET_ANCESTOR,
        "TARGET_SOURCE": TARGET_SOURCE,
        "CANONICAL_ENTRYPOINT": CANONICAL_ENTRYPOINT,
        "CANONICAL_SUPPORT_ROOT": CANONICAL_SUPPORT_ROOT,
        "ENTRYPOINT": CANONICAL_ENTRYPOINT,
        "SUPPORT_ROOT": CANONICAL_SUPPORT_ROOT,
        "PACKAGE_ROOT": CANONICAL_SUPPORT_ROOT / "deploy_executor",
        "TARGET_FILENAME": TARGET_FILENAME,
        "TARGET_OLD_BLOB": TARGET_OLD_BLOB,
        "TARGET_NEW_BLOB": TARGET_NEW_BLOB,
        "TARGET_OLD_SHA256": TARGET_OLD_SHA256,
        "TARGET_NEW_SHA256": TARGET_NEW_SHA256,
        "UPGRADE_CONTRACT_RELATIVE": UPGRADE_CONTRACT_RELATIVE,
        "CHECKOUT_CONTRACT_RELATIVE": CHECKOUT_CONTRACT_RELATIVE,
        "UPGRADE_ENTRYPOINT_RELATIVE": UPGRADE_ENTRYPOINT_RELATIVE,
        "UPGRADE_MODULE_RELATIVE": UPGRADE_MODULE_RELATIVE,
        "TEMP_NAME": TEMP_NAME,
        "ROOT_UID": ROOT_UID,
        "ROOT_GID": ROOT_GID,
        "_validate_upgrade_contract": _validate_upgrade_contract,
        "_derive_checkout": _derive_checkout,
        "_receipt": _receipt,
    }
    for name, value in bindings.items():
        setattr(_engine, name, value)


_configure_engine()

_run_git = _engine._run_git
_git_blob_sha_at = _engine._git_blob_sha_at
_install_artifacts = _engine._install_artifacts
_source_diff_guard = _engine._source_diff_guard
_validate_installed_closure = _engine._validate_installed_closure
_replace_exact_target = _engine._replace_exact_target
execute_upgrade = _engine.execute_upgrade
