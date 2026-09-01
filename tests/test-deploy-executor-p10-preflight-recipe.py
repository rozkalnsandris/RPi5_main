#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops" / "deploy" / "p10-dashboard-preflight.json"

EXPECTED_SHA = "5f7739348f56398d0ba301c9320e1de0062838fc"
NEW_CONTROLLER_BLOB = "c0566adb76e044632a4556dbefeb0f46839b4996"
LEGACY_CONTROLLER_BLOB = "7fcc58cbea2f1247d6e4d93bc3805923697fbfab"


def main() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert contract["schema_version"] == 1
    assert contract["status"] == "SOURCE_ONLY_PREFLIGHT_CONTRACT"
    assert contract["roadmap_issue"] == 236

    queue = contract["queue"]
    assert queue == {
        "repository": "rozkalnsandris/ops-workflows",
        "issue": 28,
        "required_status_before_plan": "WAITING",
        "target": "dashboard-rpi5-production-release",
    }

    source = contract["source"]
    assert source["repository"] == "rozkalnsandris/dashboard_RPi5"
    assert source["sha"] == EXPECTED_SHA
    assert source["node_major"] == 24

    prerequisites = contract["trusted_host_prerequisites"]
    assert prerequisites["read_only_presence_checks_only"] is True
    assert prerequisites["package_install_allowed"] is False
    assert prerequisites["package_upgrade_allowed"] is False
    assert {"/usr/bin/node", "npm", "git", "make", "python3"} <= set(
        prerequisites["required_commands"]
    )
    assert prerequisites["required_cxx_any_of"] == ["c++", "g++"]

    preparation = contract["candidate_preparation"]
    assert preparation["unprivileged_only"] is True
    assert preparation["clean_exact_sha_workspace_required"] is True
    assert preparation["native_build_absent_is_stop"] is True
    assert preparation["manifest_generation_requires_staged_native_runtime"] is True
    assert preparation["native_runtime_required_path"] == (
        "apps/terminal-agent/dist/native/node-pty"
    )

    expected_commands = [
        "npm ci --ignore-scripts",
        "npm audit --audit-level=high",
        (
            "npm_config_build_from_source=true npm rebuild node-pty "
            "--dangerously-allow-all-scripts --foreground-scripts"
        ),
        "npm run typecheck",
        "npm run lint",
        "npm run test",
        "npm run build",
        "node tools/package-terminal-native-runtime.mjs --root .",
        (
            "node tools/production-candidate-manifest.mjs --root . --sha "
            f"{EXPECTED_SHA} > <fresh-candidate-manifest-path>"
        ),
        (
            "node tools/production-candidate-manifest.mjs --root . --sha "
            f"{EXPECTED_SHA} --verify <fresh-candidate-manifest-path>"
        ),
        (
            "node tools/production-runtime-smoke.mjs --root . --manifest "
            f"<fresh-candidate-manifest-path> --sha {EXPECTED_SHA}"
        ),
    ]
    assert preparation["ordered_commands"] == expected_commands

    for command in preparation["ordered_commands"]:
        assert "sudo " not in command
        assert "--apply" not in command
        assert "apt-get" not in command

    controller = contract["controller"]
    assert controller["canonical_path"] == (
        "/opt/dashboard_RPi5/current/tools/production-release-controller.mjs"
    )
    assert controller["privileged_code_from_candidate_checkout_forbidden"] is True
    assert controller["installed_controller_replacement_forbidden"] is True
    assert controller["identity_algorithm"] == "git-blob-sha1"
    assert controller["identity_command"] == (
        "git hash-object --no-filters "
        "/opt/dashboard_RPi5/current/tools/production-release-controller.mjs"
    )
    assert "sha1sum" not in controller["identity_command"]

    identities = {entry["git_blob"]: entry for entry in controller["accepted_identities"]}
    assert set(identities) == {NEW_CONTROLLER_BLOB, LEGACY_CONTROLLER_BLOB}
    assert identities[NEW_CONTROLLER_BLOB]["classification"] == "new-symlink-safe"
    assert identities[NEW_CONTROLLER_BLOB]["node_extra_args"] == []
    assert identities[LEGACY_CONTROLLER_BLOB]["classification"] == "reviewed-legacy"
    assert identities[LEGACY_CONTROLLER_BLOB]["node_extra_args"] == [
        "--preserve-symlinks-main"
    ]

    assert controller["identity_selection_before_privileged_plan"] is True
    assert controller["trial_invocation_forbidden"] is True
    assert controller["max_privileged_plan_attempts"] == 1
    assert controller["plan_only"] is True
    assert controller["apply_flag_forbidden"] is True
    assert controller["acknowledgement_forbidden"] is True
    assert controller["process_exit_zero_alone_sufficient"] is False
    assert controller["required_plan_fields"] == [
        "status",
        "sourceSha",
        "candidateSha256",
        "observedCurrent",
        "targetRelease",
        "operations",
    ]

    failure = contract["failure_contract"]
    assert failure == {
        "any_preflight_error_is_stop": True,
        "retry_allowed": False,
        "cleanup_allowed": False,
        "alternate_controller_path_allowed": False,
        "apply_allowed": False,
        "production_mutation_allowed": False,
    }


if __name__ == "__main__":
    main()
