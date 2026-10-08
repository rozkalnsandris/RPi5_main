#!/usr/bin/env python3
"""Adversarial source-level regression for SIMPLE-DEPLOY pointer diagnostics."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"
spec = importlib.util.spec_from_file_location("simple_deploy_926", SOURCE)
assert spec and spec.loader
sd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sd
spec.loader.exec_module(sd)

POINTER_ARGV = (
    "docker", "buildx", "imagetools", "inspect",
    "ghcr.io/rozkalnsandris/rozkalns-cv:production",
    "--format", "{{json .Manifest}}",
)


class FailedRunner:
    def __init__(self, stderr):
        self.stderr = stderr
        self.calls = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append((tuple(argv), timeout_seconds))
        return sd.CommandResult(1, "", self.stderr)


class PointerFailureTests(unittest.TestCase):
    def test_fixed_allowlisted_failure_classes(self):
        cases = (
            ("docker: 'buildx' is not a docker command.", "BUILDX_PLUGIN_UNAVAILABLE"),
            ("unknown command \"buildx\"", "BUILDX_PLUGIN_UNAVAILABLE"),
            ("x509: certificate signed by unknown authority", "TLS_FAILURE"),
            ("TLS handshake timeout", "TLS_FAILURE"),
            ("dial tcp: lookup ghcr.io: no such host", "DNS_FAILURE"),
            ("temporary failure in name resolution", "DNS_FAILURE"),
            ("401 Unauthorized", "REGISTRY_AUTH_FAILURE"),
            ("403 Forbidden", "REGISTRY_AUTH_FAILURE"),
            ("insufficient_scope", "REGISTRY_AUTH_FAILURE"),
            ("manifest unknown", "MANIFEST_UNAVAILABLE"),
            ("connection refused", "NETWORK_FAILURE"),
            ("context deadline exceeded", "NETWORK_FAILURE"),
            ("i/o timeout", "NETWORK_FAILURE"),
            ("rpc error: mysterious internal failure", "UNCLASSIFIED"),
            ("failed to fetch anonymous token", "UNCLASSIFIED"),
            ("", "UNCLASSIFIED"),
        )
        for stderr, expected in cases:
            with self.subTest(stderr=stderr):
                self.assertEqual(sd._classify_pointer_stderr(stderr), expected)

    def test_specific_dns_tls_outrank_generic_auth_or_network(self):
        self.assertEqual(sd._classify_pointer_stderr(
            "failed to fetch anonymous token: 401 unauthorized: lookup ghcr.io: no such host"
        ), "DNS_FAILURE")
        self.assertEqual(sd._classify_pointer_stderr(
            "i/o timeout, tls handshake failure, 401 unauthorized"
        ), "TLS_FAILURE")

    def test_malformed_untrusted_and_oversized_stderr_fails_closed(self):
        self.assertEqual(sd._classify_pointer_stderr(None), "UNCLASSIFIED")
        self.assertEqual(sd._classify_pointer_stderr(b"401 unauthorized"), "UNCLASSIFIED")
        self.assertEqual(sd._classify_pointer_stderr(
            "unknown " * 1200 + "no such host"
        ), "UNCLASSIFIED")

    def test_pointer_preserves_code_and_no_mutation(self):
        secret = "TOKEN_SENTINEL_DO_NOT_EMIT"
        runner = FailedRunner("401 unauthorized\n" + secret)
        with self.assertRaises(sd.SimpleDeployError) as cm:
            sd._run_required(
                runner, POINTER_ARGV, timeout_seconds=30,
                code="POINTER_RESOLUTION_FAILED", mutation_started=False
            )
        exc = cm.exception
        self.assertEqual(exc.code, "POINTER_RESOLUTION_FAILED")
        self.assertFalse(exc.mutation_started)
        self.assertEqual(exc.failure_class, "REGISTRY_AUTH_FAILURE")
        self.assertNotIn(secret, str(exc))
        self.assertEqual(runner.calls, [(POINTER_ARGV, 30)])

    def test_non_pointer_code_does_not_gain_diagnostic_class(self):
        runner = FailedRunner("401 unauthorized")
        with self.assertRaises(sd.SimpleDeployError) as cm:
            sd._run_required(
                runner, POINTER_ARGV, timeout_seconds=30,
                code="IMAGE_METADATA_FAILED", mutation_started=False
            )
        self.assertEqual(cm.exception.code, "IMAGE_METADATA_FAILED")
        self.assertIsNone(cm.exception.failure_class)

    def test_transport_failure_enums_are_fixed_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = sd.SubprocessCommandRunner(state_root=Path(tmp))
            for synthetic_error, expected in (
                (subprocess.TimeoutExpired(["docker"], 30), "COMMAND_TIMEOUT"),
                (FileNotFoundError("PRIVATE_SENTINEL"), "COMMAND_UNAVAILABLE"),
                (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "secret"), "OUTPUT_DECODE_FAILURE"),
            ):
                with self.subTest(class_name=expected):
                    with patch.object(sd.subprocess, "run", side_effect=synthetic_error):
                        with self.assertRaises(sd.SimpleDeployError) as cm:
                            sd._run_required(
                                runner, POINTER_ARGV, timeout_seconds=30,
                                code="POINTER_RESOLUTION_FAILED", mutation_started=False
                            )
                    self.assertFalse(cm.exception.mutation_started)
                    self.assertEqual(cm.exception.code, "POINTER_RESOLUTION_FAILED")
                    self.assertEqual(cm.exception.failure_class, expected)
                    self.assertNotIn("PRIVATE_SENTINEL", str(cm.exception))

    def test_only_allowlisted_class_can_be_emitted(self):
        exc = sd.SimpleDeployError(
            "POINTER_RESOLUTION_FAILED", "safe",
            failure_class="PASSWORD_SENTINEL_private_secret",
        )
        self.assertIsNone(exc.failure_class)

    def test_main_sanitizes_exact_target_message(self):
        fake = types.SimpleNamespace(
            registry=types.SimpleNamespace(execution_enabled=True, targets=[]),
            reconcile=lambda alias: (_ for _ in ()).throw(sd.SimpleDeployError(
                "POINTER_RESOLUTION_FAILED", "secret should not be emitted",
                mutation_started=False, failure_class="DNS_FAILURE"
            )),
        )
        output = StringIO()
        with patch.object(sd, "_production_deployer", return_value=fake):
            with redirect_stdout(output):
                rc = sd.main(["--target", "rozkalns-cv-rpi5"])
        self.assertEqual(rc, 1)
        self.assertEqual(
            output.getvalue(),
            "SIMPLE_DEPLOY result=FAIL target=rozkalns-cv-rpi5 "
            "error_code=POINTER_RESOLUTION_FAILED mutation_started=false "
            "failure_class=DNS_FAILURE\n",
        )
        self.assertNotIn("secret", output.getvalue())

    def test_unrelated_errors_stay_identical(self):
        fake = types.SimpleNamespace(
            registry=types.SimpleNamespace(execution_enabled=True, targets=[]),
            reconcile=lambda alias: (_ for _ in ()).throw(sd.SimpleDeployError(
                "COMPOSE_PULL_FAILED", "sensitive data", mutation_started=True
            )),
        )
        output = StringIO()
        with patch.object(sd, "_production_deployer", return_value=fake):
            with redirect_stdout(output):
                rc = sd.main(["--target", "rozkalns-cv-rpi5"])
        self.assertEqual(rc, 1)
        self.assertEqual(output.getvalue(),
            "SIMPLE_DEPLOY result=FAIL target=rozkalns-cv-rpi5 "
            "error_code=COMPOSE_PULL_FAILED mutation_started=true\n")

    def test_no_new_mutation_or_runtime_surface(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('"{{json .Manifest}}"', source)
        self.assertIn('DOCKER_CONFIG', source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn('["docker", "login"]', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
