from __future__ import annotations

import importlib.util
import json
from pathlib import Path

RECOVERY = Path("ops/recovery/weather_v9_capability_state_bootstrap.py")
CONTRACT = Path("ops/recovery/weather_v9_capability_state_bootstrap.contract.json")


def _load_recovery():
    spec = importlib.util.spec_from_file_location("weather_v9_state_bootstrap", RECOVERY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_is_bounded_and_fail_closed():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["issue"] == 623
    assert payload["accepted_baseline"] == {"registration": "absent", "state_db": "absent"}
    assert payload["fail_closed"] is True
    assert payload["registration_published_last"] is True
    forbidden = "\n".join(payload["forbidden_mutations"])
    assert "systemctl" in forbidden
    assert "generic root shell execution" in forbidden


def test_recovery_has_fixed_canonical_paths():
    module = _load_recovery()
    assert str(module.REGISTRATION_PATH) == "/etc/rozkalns-weather-operator-v9-capability/registration.json"
    assert str(module.STATE_DB_PATH) == "/var/lib/rozkalns-weather-operator-v9-capability/state.sqlite3"
    assert str(module.SUPPORT_MODULE_PATH).startswith("/usr/local/libexec/rozkalns-weather-public-runtime-operator/")
    assert str(module.BROKER_PATH).startswith("/usr/local/libexec/rozkalns-weather-public-runtime-operator/")


def test_source_introduces_no_systemctl_sudo_or_shell_true():
    source = RECOVERY.read_text(encoding="utf-8")
    assert "systemctl" not in source
    assert "sudo" not in source
    assert "shell=True" not in source
    assert "subprocess" not in source


def test_registration_is_written_after_state_bootstrap():
    source = RECOVERY.read_text(encoding="utf-8")
    bootstrap = source.index("state_store_type(STATE_DB_PATH, bootstrap=True)")
    publish = source.index("_write_registration(registration)")
    assert bootstrap < publish


def test_mixed_or_present_state_is_rejected_before_bootstrap():
    source = RECOVERY.read_text(encoding="utf-8")
    guard = source.index("if registration_exists or state_exists:")
    bootstrap = source.index("state_store_type(STATE_DB_PATH, bootstrap=True)")
    assert guard < bootstrap


def test_staging_residue_is_rejected_before_bootstrap():
    source = RECOVERY.read_text(encoding="utf-8")
    registration_staging_guard = source.index("_require_absent(REGISTRATION_STAGING_PATH)")
    state_staging_guard = source.index("_require_absent(STATE_STAGING_PATH)")
    bootstrap = source.index("state_store_type(STATE_DB_PATH, bootstrap=True)")
    assert registration_staging_guard < bootstrap
    assert state_staging_guard < bootstrap
