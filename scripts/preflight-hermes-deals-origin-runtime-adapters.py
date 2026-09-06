#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_origin_host_evidence import HOST_OBSERVATION_SCHEMA  # noqa: E402
from deploy_executor.hermes_deals_origin_runtime_adapters import (  # noqa: E402
    ConcreteDurableHermesOriginReplayAuthority,
    ConcreteLocalHermesOriginHostObservationProvider,
    HermesOriginRuntimeAdapterError,
    REVIEWED_HERMES_SOURCE_SHA,
)

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class RuntimeAdapterPreflightError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise RuntimeAdapterPreflightError(message)


def _require_source(expected_sha: str) -> None:
    if SHA_RE.fullmatch(expected_sha) is None:
        _fail("expected RPi5 source SHA is malformed")
    result = subprocess.run(
        ("/usr/bin/git", "rev-parse", "HEAD"),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    if result.returncode != 0 or result.stdout.decode("ascii", "strict").strip() != expected_sha:
        _fail("RPi5 checkout does not match expected source SHA")


def _receipt(result: str, expected_sha: str, **extra: object) -> str:
    value: dict[str, object] = {
        "schema": "rozkalns.hermes-deals.origin-runtime-adapters-preflight.v1",
        "result": result,
        "source_sha": expected_sha,
        "registered_source_sha": REVIEWED_HERMES_SOURCE_SHA,
        "source_app_installation_scope_proven": False,
        "credential_content_read": False,
        "github_api_request": False,
        "installation_token_minted": False,
        "durable_replay_adapter_runtime_proven": False,
        "host_observation_adapter_runtime_proven": False,
        "replay_consume_invoked": False,
        "replay_mutation_started": False,
        "filesystem_mutation": False,
        "systemd_interaction": False,
        "socket_request_sent": False,
        "helper_executed": False,
        "broker_entrypoint_wired": False,
        "privileged_dispatch_enabled": False,
        "genuine_audit_authorized": False,
        "production_mutation_started": False,
    }
    value.update(extra)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Hermes concrete runtime-adapter preflight",
    )
    parser.add_argument("expected_source_sha")
    args = parser.parse_args(argv)
    try:
        _require_source(args.expected_source_sha)
        if os.geteuid() != 0:
            _fail("runtime-adapter preflight requires root read context")
        replay = ConcreteDurableHermesOriginReplayAuthority().preflight()
        if replay != {
            "durable_replay_adapter_runtime_proven": True,
            "availability_read_only": True,
            "consume_invoked": False,
            "replay_mutation_started": False,
            "production_mutation_started": False,
        }:
            _fail("durable replay adapter preflight receipt drifted")
        raw = ConcreteLocalHermesOriginHostObservationProvider().read()
        try:
            observation = json.loads(raw.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _fail("host observation provider returned malformed JSON")
        if type(observation) is not dict or observation.get("schema") != HOST_OBSERVATION_SCHEMA:
            _fail("host observation provider schema drifted")
        expected_false = (
            "credential_content_read",
            "protected_values_included",
            "filesystem_mutation",
            "systemd_interaction",
            "authority_expanded",
            "production_mutation_started",
        )
        if any(observation.get(field) is not False for field in expected_false):
            _fail("host observation provider expanded authority")
        if observation.get("registered_source_sha") != REVIEWED_HERMES_SOURCE_SHA:
            _fail("host observation provider source identity drifted")
        print(
            _receipt(
                "HERMES_ORIGIN_RUNTIME_ADAPTERS_READY",
                args.expected_source_sha,
                durable_replay_adapter_runtime_proven=True,
                host_observation_adapter_runtime_proven=True,
            )
        )
        return 0
    except (RuntimeAdapterPreflightError, HermesOriginRuntimeAdapterError):
        print(_receipt("FAIL_CLOSED", args.expected_source_sha, reason="runtime_adapter_preflight_failed"))
        return 1
    except Exception:
        print(_receipt("FAIL_CLOSED", args.expected_source_sha, reason="runtime_adapter_preflight_failed"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
