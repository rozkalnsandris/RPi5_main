#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "cloudflare_rdc_operator.py"
CONTRACT = ROOT / "ops" / "contracts" / "cloudflare-rdc-operator-v1.json"

spec = importlib.util.spec_from_file_location("cloudflare_rdc_operator", SOURCE)
assert spec and spec.loader
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)

WILDCARD_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
TARGET_ID = "33333333-3333-4333-8333-333333333333"


def wildcard_app() -> dict:
    return {
        "id": WILDCARD_ID,
        "name": "homelab-private",
        "type": "self_hosted",
        "domain": "*.rozkalns.net",
        "updated_at": "before",
    }


def other_app() -> dict:
    return {
        "id": OTHER_ID,
        "name": "Hermes Tech Public",
        "type": "self_hosted",
        "destinations": [{"type": "public", "uri": "tech.rozkalns.net"}],
    }


def target_app() -> dict:
    return {
        "id": TARGET_ID,
        "name": "Coloring Pages Public",
        "type": "self_hosted",
        "destinations": [{"type": "public", "uri": "coloring.rozkalns.net"}],
    }


class FakeClient:
    def __init__(self) -> None:
        self.created_bodies = []
        self.list_calls = 0

    def list_applications(self, account_id: str):
        self.list_calls += 1
        if self.list_calls == 1:
            return [wildcard_app(), other_app()]
        wildcard = wildcard_app()
        wildcard["updated_at"] = "after"
        return [wildcard, other_app(), target_app()]

    def create_application(self, account_id: str, body: dict):
        self.created_bodies.append(body)
        return target_app()

    def list_application_policies(self, account_id: str, app_id: str):
        self.assert_id = app_id
        return [{
            "id": "44444444-4444-4444-8444-444444444444",
            "name": "public-access",
            "decision": "bypass",
            "include": [{"everyone": {}}],
            "require": [],
            "exclude": [],
        }]


class ProvisionClient:
    def __init__(self) -> None:
        self.active_checks = 0
        self.access_checks = 0

    def verify_active_token(self) -> None:
        self.active_checks += 1

    def verify_access_permission(self, account_id: str) -> None:
        self.access_checks += 1


class CloudflareRdcOperatorTests(unittest.TestCase):
    def test_create_body_is_one_exact_inline_public_bypass(self) -> None:
        self.assertEqual(
            op.build_create_body(),
            {
                "name": "Coloring Pages Public",
                "type": "self_hosted",
                "destinations": [
                    {"type": "public", "uri": "coloring.rozkalns.net"}
                ],
                "policies": [{
                    "name": "public-access",
                    "decision": "bypass",
                    "include": [{"everyone": {}}],
                }],
            },
        )

    def test_preflight_accepts_parent_wildcard_and_absent_exact_app(self) -> None:
        report = op.preflight_applications([wildcard_app(), other_app()])
        self.assertTrue(report["parent_wildcard_present"])
        self.assertTrue(report["exact_target_absent"])
        self.assertEqual(
            set(report["preexisting_apps"]), {WILDCARD_ID, OTHER_ID}
        )

    def test_preflight_refuses_existing_exact_target(self) -> None:
        with self.assertRaisesRegex(
            op.OperatorError, "exact_target_application_already_exists"
        ):
            op.preflight_applications([wildcard_app(), target_app()])

    def test_preflight_refuses_missing_parent_wildcard(self) -> None:
        with self.assertRaisesRegex(
            op.OperatorError, "parent_wildcard_missing_or_ambiguous"
        ):
            op.preflight_applications([other_app()])

    def test_preflight_refuses_path_specific_exact_target(self) -> None:
        path_target = target_app()
        path_target["destinations"] = [
            {"type": "public", "uri": "coloring.rozkalns.net/private"}
        ]
        with self.assertRaisesRegex(
            op.OperatorError, "exact_target_application_already_exists"
        ):
            op.preflight_applications([wildcard_app(), path_target])

    def test_apply_uses_one_create_call_and_get_only_post_verification(self) -> None:
        client = FakeClient()
        result = op.run_operator(client, "a" * 32, apply=True)
        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["mutation_performed"])
        self.assertEqual(len(client.created_bodies), 1)
        self.assertEqual(client.created_bodies[0], op.build_create_body())
        self.assertEqual(client.assert_id, TARGET_ID)

    def test_dry_run_never_calls_create(self) -> None:
        client = FakeClient()
        result = op.run_operator(client, "a" * 32, apply=False)
        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["apply_ready"])
        self.assertEqual(client.created_bodies, [])
        self.assertEqual(client.list_calls, 1)

    def test_post_write_rejects_unrelated_application_change(self) -> None:
        before = op.preflight_applications([wildcard_app(), other_app()])
        changed = other_app()
        changed["name"] = "changed"
        policies = [{
            "name": "public-access",
            "decision": "bypass",
            "include": [{"everyone": {}}],
        }]
        with self.assertRaisesRegex(
            op.OperatorError, "preexisting_application_changed_after_write"
        ):
            op.verify_post_write(
                before,
                [wildcard_app(), changed, target_app()],
                policies,
                TARGET_ID,
            )

    def test_controlling_tty_precheck_requires_real_tty(self) -> None:
        with mock.patch.object(op.os, "open", return_value=9), \
             mock.patch.object(op.os, "isatty", return_value=True) as isatty, \
             mock.patch.object(op.os, "close") as close:
            op._ensure_controlling_tty()
        isatty.assert_called_once_with(9)
        close.assert_called_once_with(9)

        with mock.patch.object(op.os, "open", side_effect=OSError("no tty")):
            with self.assertRaisesRegex(op.OperatorError, "local_tty_required"):
                op._ensure_controlling_tty()

    def test_hidden_credentials_use_native_getpass_without_custom_stream(self) -> None:
        with mock.patch.object(op, "_ensure_controlling_tty"), \
             mock.patch.object(
                 op.getpass,
                 "getpass",
                 side_effect=["a" * 32, "t" * 32],
             ) as prompt:
            account_id, token = op._read_hidden_provisioning_credentials()
        self.assertEqual(account_id, "a" * 32)
        self.assertEqual(token, "t" * 32)
        self.assertEqual(
            prompt.call_args_list,
            [
                mock.call("Cloudflare account ID: "),
                mock.call("Cloudflare Access API token: "),
            ],
        )

    def test_getpass_warning_fails_closed_instead_of_echo_fallback(self) -> None:
        with mock.patch.object(op, "_ensure_controlling_tty"), \
             mock.patch.object(
                 op.getpass,
                 "getpass",
                 side_effect=op.getpass.GetPassWarning("echo unavailable"),
             ):
            with self.assertRaisesRegex(op.OperatorError, "local_tty_required"):
                op._read_hidden_provisioning_credentials()

    def test_provision_action_has_no_token_or_account_id_cli_argument(self) -> None:
        args = op.parse_args([
            "provision-access-secret",
            "--expected-main",
            "a" * 40,
            "--confirm",
            "PROVISION-CLOUDFLARE-ACCESS-SECRET",
        ])
        self.assertEqual(args.action, "provision-access-secret")
        self.assertFalse(hasattr(args, "api_token"))
        self.assertFalse(hasattr(args, "account_id"))
        with self.assertRaises(SystemExit):
            op.parse_args([
                "provision-access-secret",
                "--expected-main",
                "a" * 40,
                "--api-token",
                "forbidden",
            ])

    def test_provision_preflights_token_before_secret_write(self) -> None:
        client = ProvisionClient()
        secret_path = mock.Mock()
        secret_path.exists.return_value = False
        with mock.patch.object(op, "ACCESS_SECRET_PATH", secret_path), \
             mock.patch.object(op, "_write_access_secret") as writer:
            op.provision_access_secret(client, "a" * 32, "t" * 32)
        self.assertEqual(client.active_checks, 1)
        self.assertEqual(client.access_checks, 1)
        writer.assert_called_once_with("a" * 32, "t" * 32)

    def test_contract_separates_access_tunnel_and_dns_credentials(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        lanes = contract["secret_lanes"]
        self.assertEqual(set(lanes), {"access", "tunnel", "dns"})
        self.assertEqual(len({item["path"] for item in lanes.values()}), 3)
        self.assertTrue(lanes["access"]["implemented"])
        self.assertTrue(lanes["tunnel"]["implemented"])
        self.assertTrue(lanes["dns"]["implemented"])
        self.assertEqual(
            lanes["access"]["cloudflare_permission"],
            "Access: Apps and Policies Write",
        )
        self.assertEqual(
            lanes["tunnel"]["cloudflare_permission"],
            "Cloudflare One Connector: cloudflared Write",
        )
        self.assertEqual(
            lanes["tunnel"]["shared_capability_contract"],
            "ops/contracts/cloudflare-tunnel-operator-v1.json",
        )
        self.assertIn("same Tunnel-only credential", lanes["tunnel"]["credential_reuse"])
        self.assertEqual(lanes["dns"]["scope"], "zone:ausmalwiese.de")

    def test_contract_freezes_unprivileged_installer_and_local_tty_secret_flow(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        bootstrap = contract["host_bootstrap"]
        install = bootstrap["install"]
        self.assertFalse(install["root_executes_repository_python"])
        self.assertFalse(install["sudoers_mutation"])
        self.assertTrue(install["requires_clean_exact_main"])
        provision = bootstrap["access_secret_provisioning"]
        self.assertEqual(provision["input_channel"], "hidden controlling TTY only")
        self.assertTrue(provision["argv_secret_forbidden"])
        self.assertTrue(provision["environment_secret_forbidden"])
        self.assertTrue(provision["rdc_secret_input_forbidden"])
        self.assertEqual(
            provision["required_token_scope"],
            "Access: Apps and Policies Write only",
        )
        self.assertFalse(provision["overwrite_existing_secret"])
        self.assertFalse(provision["automatic_retry"])
        self.assertFalse(
            provision["automatic_rollback_or_cleanup_after_mutation_error"]
        )

    def test_contract_freezes_native_getpass_and_exact_release_upgrade(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        provision = contract["host_bootstrap"]["access_secret_provisioning"]
        self.assertIn("/dev/tty", provision["tty_precheck"])
        self.assertIn("no custom stream", provision["getpass_stream"])
        self.assertIn("GetPassWarning is fatal", provision["getpass_warning_policy"])
        upgrade = contract["host_bootstrap"]["upgrade"]
        self.assertTrue(upgrade["expected_installed_release_required"])
        self.assertTrue(
            upgrade["root_helper_revalidates_installed_release_before_first_upgrade_mutation"]
        )
        self.assertFalse(upgrade["root_executes_repository_python"])
        self.assertFalse(upgrade["secret_or_cloudflare_access"])
        self.assertFalse(upgrade["sudoers_mutation"])
        self.assertFalse(upgrade["automatic_retry"])
        self.assertFalse(upgrade["automatic_rollback"])
        self.assertFalse(upgrade["automatic_cleanup_after_mutation_error"])
        self.assertEqual(
            upgrade["fixed_stage_paths"],
            [
                "/usr/local/sbin/rpi5-cloudflare.next",
                "/usr/local/libexec/rpi5-cloudflare/release.json.next",
            ],
        )

    def test_contract_enforces_single_write_and_no_retry_or_rollback(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        operation = contract["operations"][0]
        self.assertEqual(operation["max_write_requests"], 1)
        self.assertEqual(operation["cloudflare_method"], "POST")
        forbidden = set(contract["forbidden"])
        self.assertIn("automatic retry", forbidden)
        self.assertIn(
            "automatic rollback or cleanup after write uncertainty",
            forbidden,
        )
        self.assertIn("API Tokens Edit permission", forbidden)


    def test_tunnel_hidden_credentials_use_separate_prompt(self) -> None:
        with mock.patch.object(op, "_ensure_controlling_tty"), \
             mock.patch.object(
                 op.getpass,
                 "getpass",
                 side_effect=["a" * 32, "t" * 32],
             ) as prompt:
            account_id, token = op._read_hidden_tunnel_provisioning_credentials()
        self.assertEqual(account_id, "a" * 32)
        self.assertEqual(token, "t" * 32)
        self.assertEqual(
            prompt.call_args_list,
            [
                mock.call("Cloudflare account ID: "),
                mock.call("Cloudflare Tunnel API token: "),
            ],
        )

    def test_tunnel_provision_action_has_no_secret_cli_fields(self) -> None:
        args = op.parse_args([
            "provision-tunnel-secret",
            "--expected-main",
            "a" * 40,
            "--confirm",
            "PROVISION-CLOUDFLARE-TUNNEL-SECRET",
        ])
        self.assertEqual(args.action, "provision-tunnel-secret")
        for name in ("api_token", "account_id", "secret_path"):
            self.assertFalse(hasattr(args, name))

    def test_phase7_root_git_checkout_disables_optional_index_writes(self) -> None:
        expected_main = "b" * 40
        seen = []

        def runner(argv, **kwargs):
            self.assertEqual(argv[:2], ["/usr/bin/git", "--no-optional-locks"])
            self.assertEqual(
                argv[2:6],
                ["-c", f"safe.directory={ROOT}", "-C", str(ROOT)],
            )
            operation = argv[6:]
            seen.append(operation)
            outputs = {
                ("rev-parse", "--show-toplevel"): str(ROOT),
                ("branch", "--show-current"): "main",
                ("remote", "get-url", "origin"):
                    "https://github.com/rozkalnsandris/RPi5_main.git",
                ("status", "--porcelain=v1", "--untracked-files=all"): "",
                ("rev-parse", "HEAD"): expected_main,
                ("ls-files", "--error-unmatch", "scripts/ingress_drift_audit.py"):
                    "scripts/ingress_drift_audit.py",
            }
            result = outputs.get(tuple(operation))
            self.assertIsNotNone(result)
            return subprocess.CompletedProcess(
                argv, 0, stdout=result + "\n", stderr="",
            )

        audit_path = op.verify_phase7_checkout(
            expected_main, ROOT, runner=runner,
        )
        self.assertEqual(audit_path, ROOT / "scripts" / "ingress_drift_audit.py")
        self.assertIn(
            ["status", "--porcelain=v1", "--untracked-files=all"], seen,
        )
        self.assertEqual(len(seen), 6)

    def test_phase7_runtime_action_passes_token_only_on_stdin(self) -> None:
        token = "t" * 32
        account_id = "a" * 32
        expected = "b" * 40
        report = {
            "schema": "rozkalns.rpi5-main.ingress-drift-audit-evidence.v1",
            "source_main_sha": expected,
            "mutation_performed": False,
            "result": "PASS",
        }

        def runner(argv, **kwargs):
            self.assertEqual(
                argv,
                [
                    "/usr/bin/python3",
                    "/fixed/ingress_drift_audit.py",
                    "--expected-main",
                    expected,
                ],
            )
            self.assertEqual(kwargs["input"], (token + "\n").encode("utf-8"))
            self.assertEqual(kwargs["env"]["CLOUDFLARE_ACCOUNT_ID"], account_id)
            self.assertEqual(kwargs["env"]["GIT_CONFIG_COUNT"], "1")
            self.assertEqual(kwargs["env"]["GIT_CONFIG_KEY_0"], "safe.directory")
            self.assertEqual(kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")
            self.assertEqual(
                kwargs["env"]["GIT_CONFIG_VALUE_0"],
                "/fixed/checkout",
            )
            self.assertNotIn("CLOUDFLARE_API_TOKEN", kwargs["env"])
            self.assertNotIn("CLOUDFLARE_TUNNEL_ID", kwargs["env"])
            self.assertNotIn(token, argv)
            self.assertNotIn(token, kwargs["env"].values())
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(report).encode("utf-8"),
                stderr=b"",
            )

        rc, observed = op.run_phase7_audit(
            Path("/fixed/ingress_drift_audit.py"),
            Path("/fixed/checkout"),
            expected,
            account_id,
            token,
            runner=runner,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(observed, report)

    def test_phase7_contract_is_fixed_get_only_and_non_authorizing(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        provision = contract["host_bootstrap"]["tunnel_secret_provisioning"]
        self.assertFalse(provision["overwrite_existing_secret"])
        self.assertFalse(provision["automatic_retry"])
        self.assertFalse(provision["automatic_rollback_or_cleanup_after_mutation_error"])
        operation = contract["read_only_operations"][0]
        self.assertEqual(operation["cloudflare_methods"], ["GET"])
        self.assertFalse(operation["access_credential_reuse_allowed"])
        self.assertFalse(operation["token_in_argv_allowed"])
        self.assertFalse(operation["token_in_environment_allowed"])
        self.assertFalse(operation["mutation_allowed"])
        self.assertFalse(operation["remediation_allowed"])


    def test_user_and_account_token_verification_use_distinct_fixed_endpoints(self) -> None:
        client = op.CloudflareClient("t" * 32)
        active = {"result": {"status": "active"}}

        with mock.patch.object(client, "_request", return_value=active) as request:
            client.verify_active_token()
        request.assert_called_once_with("GET", "/user/tokens/verify")

        with mock.patch.object(client, "_request", return_value=active) as request:
            client.verify_active_account_token("a" * 32)
        request.assert_called_once_with(
            "GET",
            "/accounts/" + "a" * 32 + "/tokens/verify",
        )

    def test_account_token_verification_rejects_invalid_account_before_request(self) -> None:
        client = op.CloudflareClient("t" * 32)
        with mock.patch.object(client, "_request") as request:
            with self.assertRaisesRegex(op.OperatorError, "secret_payload_invalid"):
                client.verify_active_account_token("not-an-account")
        request.assert_not_called()

    def test_tunnel_provisioning_uses_account_token_verification_before_write(self) -> None:
        events = []

        class TunnelProvisionClient:
            def verify_active_account_token(self, account_id: str) -> None:
                events.append(("account-token", account_id))

            def verify_tunnel_permission(self, account_id: str) -> None:
                events.append(("tunnel-permission", account_id))

        secret_path = mock.Mock()
        secret_path.exists.return_value = False
        with mock.patch.object(op, "TUNNEL_SECRET_PATH", secret_path), \
             mock.patch.object(
                 op,
                 "_write_tunnel_secret",
                 side_effect=lambda account_id, token: events.append(
                     ("write", account_id, token)
                 ),
             ):
            op.provision_tunnel_secret(
                TunnelProvisionClient(),
                "a" * 32,
                "t" * 32,
            )

        self.assertEqual(
            events,
            [
                ("account-token", "a" * 32),
                ("tunnel-permission", "a" * 32),
                ("write", "a" * 32, "t" * 32),
            ],
        )



class AusmalwieseDnsTests(unittest.TestCase):
    def test_route_uses_existing_loopback_and_retains_catchall(self):
        before = {"ingress": [
            {"hostname": "coloring.rozkalns.net", "service": "http://127.0.0.1:9191"},
            {"service": "http_status:404"}],
            "originRequest": {"connectTimeout": "10s"}}
        after = op._prepared_tunnel_config(before)
        self.assertEqual([r.get("hostname") for r in after["ingress"]],
                         ["coloring.rozkalns.net", "ausmalwiese.de", "www.ausmalwiese.de", None])
        self.assertEqual(after["ingress"][1]["service"], before["ingress"][0]["service"])
        self.assertEqual(before["ingress"][-1], after["ingress"][-1])
        self.assertEqual(before["originRequest"], after["originRequest"])
        self.assertEqual(len(before["ingress"]), 2)

    def test_route_rejects_existing_host_and_non_loopback(self):
        for service in ("http://example.invalid:8080", "https://example.com", "http://127.0.0.1"):
            with self.assertRaises(op.OperatorError):
                op._prepared_tunnel_config({"ingress": [
                    {"hostname": "coloring.rozkalns.net", "service": service},
                    {"service": "http_status:404"}]})
        with self.assertRaisesRegex(op.OperatorError, "tunnel_route_conflict"):
            op._prepared_tunnel_config({"ingress": [
                {"hostname": "coloring.rozkalns.net", "service": "http://127.0.0.1:8080"},
                {"hostname": "www.ausmalwiese.de", "service": "http://127.0.0.1:8080"},
                {"service": "http_status:404"}]})

    def test_baseline_stable_and_sensitive_data_not_printed(self):
        self.assertEqual(op._baseline({"a": 1, "b": 2}), op._baseline({"b": 2, "a": 1}))
        self.assertEqual(len(op._baseline({"sample": "a"})), 64)

    def test_cli_requires_baseline_and_confirmation_before_write(self):
        args = op.parse_args(["dns-ausmalwiese-apex", "--expected-main", "a" * 40])
        self.assertFalse(args.apply)
        self.assertEqual(args.expected_baseline, "")
        self.assertEqual(args.confirm, "")
        self.assertEqual(op.parse_args(["tunnel-ausmalwiese", "--expected-main", "a" * 40]).action,
                         "tunnel-ausmalwiese")

    def test_existing_access_and_tunnel_modes_remain(self):
        source = SOURCE.read_text(encoding="utf-8")
        for value in ("access-public-bypass", "provision-access-secret",
                      "provision-tunnel-secret", "phase7-ingress-drift-audit"):
            self.assertIn(value, source)

    def test_dns_get_only_and_one_exact_write(self):
        account_id, zone_id = "a" * 32, "b" * 32
        tunnel_id = "11111111-1111-4111-8111-111111111111"

        class FakeDns:
            def __init__(self):
                self.records = []
                self.writes = []

            def _request(self, method, path, body=None):
                if method == "GET" and path == f"/zones/{zone_id}":
                    return {"result": {"id": zone_id, "name": "ausmalwiese.de",
                        "status": "active", "account": {"id": account_id},
                        "plan": {"legacy_id": "free"}}}
                if method == "GET" and "/dns_records?" in path:
                    return {"result": list(self.records), "result_info": {"total_pages": 1}}
                if method == "POST" and path == f"/zones/{zone_id}/dns_records":
                    self.writes.append(body)
                    self.records.append(body)
                    return {"result": body}
                raise AssertionError((method, path))

        class FakeTunnel:
            def __init__(self):
                self.put = []

            def _request(self, method, path, body=None):
                if method == "GET" and "/cfd_tunnel?" in path:
                    return {"result": [{"id": tunnel_id, "name": "rpi5-tunnel", "config_src": "cloudflare"}]}
                if method == "GET" and path.endswith("/configurations"):
                    return {"result": {"config": {"ingress": [
                        {"hostname": "coloring.rozkalns.net", "service": "http://127.0.0.1:8080"},
                        {"service": "http_status:404"}]}}}
                if method == "PUT":
                    self.put.append(body)
                    return {"result": body}
                raise AssertionError((method, path))

        dns, tunnel = FakeDns(), FakeTunnel()
        before = op.run_ausmalwiese(dns, tunnel, zone_id, account_id,
                                   "dns-ausmalwiese-apex", False, "")
        self.assertFalse(before["applied"])
        self.assertEqual(dns.writes, [])
        with self.assertRaisesRegex(op.OperatorError, "baseline_mismatch"):
            op.run_ausmalwiese(dns, tunnel, zone_id, account_id,
                              "dns-ausmalwiese-apex", True, "f" * 64)
        self.assertEqual(dns.writes, [])
        op.run_ausmalwiese(dns, tunnel, zone_id, account_id,
                          "dns-ausmalwiese-apex", True, before["baseline"])
        self.assertEqual(len(dns.writes), 1)
        self.assertEqual(dns.writes[0], {"type": "CNAME", "name": "ausmalwiese.de",
                           "content": tunnel_id + ".cfargotunnel.com",
                           "ttl": 1, "proxied": True})
        with self.assertRaisesRegex(op.OperatorError, "dns_record_conflict"):
            op.run_ausmalwiese(dns, tunnel, zone_id, account_id,
                              "dns-ausmalwiese-apex", False, "")
        self.assertEqual(tunnel.put, [])

    def test_dns_rejects_wrong_zone_and_partial_inventory(self):
        class Fake:
            def _request(self, method, path, body=None):
                return {"result": {"id": "b" * 32, "name": "another.de", "status": "active",
                                   "account": {"id": "a" * 32}, "plan": {"legacy_id": "free"}}}
        with self.assertRaisesRegex(op.OperatorError, "dns_zone_invalid"):
            op._ausmalwiese_zone(Fake(), "b" * 32)
        class Paginated:
            def _request(self, method, path, body=None):
                return {"result": [], "result_info": {"total_pages": 2}}
        with self.assertRaisesRegex(op.OperatorError, "dns_records_incomplete"):
            op._ausmalwiese_records(Paginated(), "b" * 32)


class AusmalwieseAdminCutoverTests(unittest.TestCase):
    ACCOUNT = "a" * 32
    ZONE = "b" * 32
    TUNNEL_ID = "11111111-1111-4111-8111-111111111111"
    DASH_ID = "55555555-5555-4555-8555-555555555555"
    ADMIN_ID = "66666666-6666-4666-8666-666666666666"
    DNS_ID = "c" * 32

    @staticmethod
    def dash_app() -> dict:
        return {
            "id": AusmalwieseAdminCutoverTests.DASH_ID,
            "name": "Dashboard",
            "type": "self_hosted",
            "destinations": [{"type": "public", "uri": "dash.rozkalns.net"}],
            "aud": "dash-aud-private",
        }

    @staticmethod
    def admin_app() -> dict:
        return {
            "id": AusmalwieseAdminCutoverTests.ADMIN_ID,
            "name": "Ausmalwiese Admin",
            "type": "self_hosted",
            "destinations": [{"type": "public", "uri": "admin.ausmalwiese.de"}],
            "aud": "admin-aud-private",
        }

    @staticmethod
    def owner_policy(name: str = "owner-only") -> dict:
        return {
            "id": "77777777-7777-4777-8777-777777777777",
            "name": name,
            "decision": "allow",
            "include": [{"email": {"email": "owner_identity_redacted"}}],
            "require": [],
            "exclude": [],
        }

    def test_access_action_privately_reuses_dashboard_exact_owner_selector(self):
        class FakeAccess:
            def __init__(inner):
                inner.created = []
                inner.created_now = False

            def list_applications(inner, account_id):
                apps = [self.dash_app()]
                if inner.created_now:
                    apps.append(self.admin_app())
                return apps

            def list_application_policies(inner, account_id, app_id):
                if app_id == self.DASH_ID:
                    return [self.owner_policy("dashboard-owner")]
                if app_id == self.ADMIN_ID:
                    return [self.owner_policy("owner-only")]
                raise AssertionError(app_id)

            def create_application(inner, account_id, body):
                inner.created.append(body)
                inner.created_now = True
                return self.admin_app()

        client = FakeAccess()
        dry = op.run_ausmalwiese_admin_access(
            client, self.ACCOUNT, apply=False, expected_baseline=""
        )
        self.assertFalse(dry["applied"])
        self.assertEqual(len(dry["baseline"]), 64)
        self.assertEqual(client.created, [])

        applied = op.run_ausmalwiese_admin_access(
            client, self.ACCOUNT, apply=True, expected_baseline=dry["baseline"]
        )
        self.assertTrue(applied["applied"])
        self.assertEqual(len(client.created), 1)
        body = client.created[0]
        self.assertEqual(body["name"], "Ausmalwiese Admin")
        self.assertEqual(
            body["destinations"],
            [{"type": "public", "uri": "admin.ausmalwiese.de"}],
        )
        self.assertEqual(body["policies"][0]["decision"], "allow")
        self.assertEqual(
            body["policies"][0]["include"],
            [{"email": {"email": "owner_identity_redacted"}}],
        )
        self.assertEqual(body["policies"][0]["require"], [])
        self.assertEqual(body["policies"][0]["exclude"], [])

    def test_access_action_rejects_broad_dashboard_policy_and_existing_target(self):
        class Broad:
            def list_applications(inner, account_id):
                return [self.dash_app()]

            def list_application_policies(inner, account_id, app_id):
                return [{
                    "name": "dashboard-owner",
                    "decision": "allow",
                    "include": [{"everyone": {}}],
                    "require": [],
                    "exclude": [],
                }]

        with self.assertRaisesRegex(op.OperatorError, "admin_template_policy_invalid"):
            op.run_ausmalwiese_admin_access(
                Broad(), self.ACCOUNT, apply=False, expected_baseline=""
            )

        class Existing(Broad):
            def list_applications(inner, account_id):
                return [self.dash_app(), self.admin_app()]

        with self.assertRaisesRegex(
            op.OperatorError, "admin_target_application_already_exists"
        ):
            op.run_ausmalwiese_admin_access(
                Existing(), self.ACCOUNT, apply=False, expected_baseline=""
            )

    def test_tunnel_action_adds_one_protected_loopback_route_before_catchall(self):
        class Access:
            def list_applications(inner, account_id):
                return [self.admin_app()]

            def list_application_policies(inner, account_id, app_id):
                return [self.owner_policy()]

            def _request(inner, method, path, body=None):
                raise AssertionError("Access organization GET must not be used")

        class Tunnel:
            def __init__(inner):
                inner.config = {
                    "ingress": [
                        {
                            "hostname": "ausmalwiese.de",
                            "service": "http://127.0.0.1:9191",
                        },
                        {
                            "hostname": "dash.rozkalns.net",
                            "service": "http://127.0.0.1:8088",
                            "originRequest": {
                                "access": {
                                    "required": True,
                                    "teamName": "private-team",
                                    "audTag": ["dashboard-aud-private"],
                                }
                            },
                        },
                        {"service": "http_status:404"},
                    ],
                    "originRequest": {"connectTimeout": "10s"},
                }
                inner.put = []

            def _request(inner, method, path, body=None):
                if method == "GET" and "/cfd_tunnel?" in path:
                    return {"result": [{
                        "id": self.TUNNEL_ID,
                        "name": "rpi5-tunnel",
                        "config_src": "cloudflare",
                    }]}
                if method == "GET" and path.endswith("/configurations"):
                    return {"result": {"config": inner.config}}
                if method == "PUT":
                    inner.put.append(body)
                    inner.config = body["config"]
                    return {"result": body}
                raise AssertionError((method, path))

        access, tunnel = Access(), Tunnel()
        dry = op.run_ausmalwiese_admin_tunnel(
            access, tunnel, self.ACCOUNT, apply=False, expected_baseline=""
        )
        self.assertFalse(dry["applied"])
        self.assertEqual(tunnel.put, [])
        applied = op.run_ausmalwiese_admin_tunnel(
            access, tunnel, self.ACCOUNT, apply=True, expected_baseline=dry["baseline"]
        )
        self.assertTrue(applied["applied"])
        self.assertEqual(len(tunnel.put), 1)
        rules = tunnel.config["ingress"]
        self.assertEqual(rules[-1], {"service": "http_status:404"})
        admin = next(r for r in rules if r.get("hostname") == "admin.ausmalwiese.de")
        self.assertEqual(admin["service"], "http://127.0.0.1:8765")
        self.assertEqual(
            admin["originRequest"]["access"],
            {
                "required": True,
                "teamName": "private-team",
                "audTag": ["admin-aud-private"],
            },
        )
        self.assertEqual(tunnel.config["originRequest"], {"connectTimeout": "10s"})

    def test_tunnel_action_rejects_missing_or_invalid_dashboard_team_anchor(self):
        class Access:
            def list_applications(inner, account_id):
                return [self.admin_app()]

            def list_application_policies(inner, account_id, app_id):
                return [self.owner_policy()]

            def _request(inner, method, path, body=None):
                raise AssertionError("Access organization GET must not be used")

        class Tunnel:
            def __init__(inner, dash_rule=None):
                rules = [
                    {
                        "hostname": "ausmalwiese.de",
                        "service": "http://127.0.0.1:9191",
                    }
                ]
                if dash_rule is not None:
                    rules.append(dash_rule)
                rules.append({"service": "http_status:404"})
                inner.config = {"ingress": rules}

            def _request(inner, method, path, body=None):
                if method == "GET" and "/cfd_tunnel?" in path:
                    return {"result": [{
                        "id": self.TUNNEL_ID,
                        "name": "rpi5-tunnel",
                        "config_src": "cloudflare",
                    }]}
                if method == "GET" and path.endswith("/configurations"):
                    return {"result": {"config": inner.config}}
                raise AssertionError((method, path))

        invalid_rules = [
            None,
            {
                "hostname": "dash.rozkalns.net",
                "service": "http://127.0.0.1:8088",
            },
            {
                "hostname": "dash.rozkalns.net",
                "service": "http://127.0.0.1:8088",
                "originRequest": {
                    "access": {
                        "required": False,
                        "teamName": "private-team",
                        "audTag": ["dashboard-aud-private"],
                    }
                },
            },
            {
                "hostname": "dash.rozkalns.net",
                "service": "http://127.0.0.1:8088",
                "originRequest": {
                    "access": {
                        "required": True,
                        "teamName": "",
                        "audTag": ["dashboard-aud-private"],
                    }
                },
            },
            {
                "hostname": "dash.rozkalns.net",
                "service": "http://127.0.0.1:8088",
                "originRequest": {
                    "access": {
                        "required": True,
                        "teamName": "private-team",
                        "audTag": [],
                    }
                },
            },
        ]
        for rule in invalid_rules:
            with self.subTest(rule=rule):
                with self.assertRaisesRegex(
                    op.OperatorError, "admin_tunnel_team_anchor_invalid"
                ):
                    op.run_ausmalwiese_admin_tunnel(
                        Access(),
                        Tunnel(rule),
                        self.ACCOUNT,
                        apply=False,
                        expected_baseline="",
                    )

    def test_dns_action_requires_protected_route_and_creates_one_exact_cname(self):
        class Tunnel:
            def __init__(inner, protected=True):
                access = {
                    "required": True,
                    "teamName": "private-team",
                    "audTag": ["admin-aud-private"],
                }
                inner.config = {
                    "ingress": [
                        {
                            "hostname": "admin.ausmalwiese.de",
                            "service": "http://127.0.0.1:8765",
                            "originRequest": {"access": access if protected else {}},
                        },
                        {"service": "http_status:404"},
                    ]
                }

            def _request(inner, method, path, body=None):
                if method == "GET" and "/cfd_tunnel?" in path:
                    return {"result": [{
                        "id": self.TUNNEL_ID,
                        "name": "rpi5-tunnel",
                        "config_src": "cloudflare",
                    }]}
                if method == "GET" and path.endswith("/configurations"):
                    return {"result": {"config": inner.config}}
                raise AssertionError((method, path))

        class Dns:
            def __init__(inner):
                inner.records = []
                inner.writes = []

            def _request(inner, method, path, body=None):
                if method == "GET" and path == f"/zones/{self.ZONE}":
                    return {"result": {
                        "id": self.ZONE,
                        "name": "ausmalwiese.de",
                        "status": "active",
                        "account": {"id": self.ACCOUNT},
                        "plan": {"legacy_id": "free"},
                    }}
                if method == "GET" and "/dns_records?" in path:
                    return {
                        "result": list(inner.records),
                        "result_info": {"total_pages": 1},
                    }
                if method == "POST" and path == f"/zones/{self.ZONE}/dns_records":
                    inner.writes.append(body)
                    row = dict(body)
                    row["id"] = self.DNS_ID
                    inner.records.append(row)
                    return {"result": row}
                raise AssertionError((method, path))

        with self.assertRaisesRegex(op.OperatorError, "admin_tunnel_route_invalid"):
            op.run_ausmalwiese_admin_dns(
                Dns(), Tunnel(False), self.ZONE, self.ACCOUNT,
                apply=False, expected_baseline=""
            )

        dns, tunnel = Dns(), Tunnel(True)
        dry = op.run_ausmalwiese_admin_dns(
            dns, tunnel, self.ZONE, self.ACCOUNT,
            apply=False, expected_baseline=""
        )
        self.assertFalse(dry["applied"])
        self.assertEqual(dns.writes, [])
        applied = op.run_ausmalwiese_admin_dns(
            dns, tunnel, self.ZONE, self.ACCOUNT,
            apply=True, expected_baseline=dry["baseline"]
        )
        self.assertTrue(applied["applied"])
        self.assertEqual(len(dns.writes), 1)
        self.assertEqual(dns.writes[0], {
            "type": "CNAME",
            "name": "admin.ausmalwiese.de",
            "content": self.TUNNEL_ID + ".cfargotunnel.com",
            "ttl": 1,
            "proxied": True,
        })

    def test_cli_and_contract_freeze_three_one_write_actions(self):
        for action in (
            "ausmalwiese-admin-access",
            "ausmalwiese-admin-tunnel",
            "ausmalwiese-admin-dns",
        ):
            args = op.parse_args([action, "--expected-main", "a" * 40])
            self.assertEqual(args.action, action)
            self.assertFalse(args.apply)
            self.assertEqual(args.expected_baseline, "")

        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in contract["operations"]}
        for op_id, method in (
            ("ausmalwiese-admin-access-v1", "POST"),
            ("ausmalwiese-admin-tunnel-v1", "PUT"),
            ("ausmalwiese-admin-dns-v1", "POST"),
        ):
            self.assertEqual(by_id[op_id]["max_write_requests"], 1)
            self.assertEqual(by_id[op_id]["cloudflare_method"], method)
        self.assertFalse(
            by_id["ausmalwiese-admin-access-v1"]["identity_source"]["emit_identity"]
        )
        self.assertEqual(
            by_id["ausmalwiese-admin-tunnel-v1"]["origin"],
            "http://127.0.0.1:8765",
        )

    def test_source_has_no_caller_selected_admin_hostname_or_origin(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('ADMIN_HOSTNAME = "admin.ausmalwiese.de"', source)
        self.assertIn('ADMIN_ORIGIN = "http://127.0.0.1:8765"', source)
        self.assertNotIn('add_argument("hostname")', source[source.index("ausmalwiese-admin-access"):])

if __name__ == "__main__":
    unittest.main()