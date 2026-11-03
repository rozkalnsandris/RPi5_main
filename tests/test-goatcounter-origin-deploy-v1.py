#!/usr/bin/env python3
"""Synthetic offline integration of preparation, installed contract and reconciler."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("origin_prepare", ROOT / "scripts/prepare-goatcounter-origin-deploy-v1.py")
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)
sd = op.sd
NOW = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)
BASE_PLATFORM = "sha256:" + "1" * 64
BASE_MANIFEST = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [{"digest": BASE_PLATFORM, "platform": {"os": "linux", "architecture": "arm64"}}]})
BASE = "sha256:" + hashlib.sha256(BASE_MANIFEST.encode()).hexdigest()
DERIVED = "sha256:" + "2" * 64
NEW_BASE = "sha256:" + "3" * 64
SOURCE = "a" * 40
HOST_SOURCE = "b" * 40
REGISTRY = (ROOT / "ops/deploy/simple-deploy-targets-v1.json").read_bytes()
COMPOSE = (ROOT / "ops/deploy/simple-deploy-compose/coloring-pages-public.yml").read_bytes()
TARGET = next(t for t in json.loads(REGISTRY)["targets"] if t["target_alias"] == sd.ORIGIN_TARGET)


def fixture():
    peer = {"schema": "rozkalns.origin-peer-evidence.v1", "host": "rpi5",
        "observed_at": "2026-11-02T19:30:00Z", "image_ref": sd.ORIGIN_IMAGE + "@" + DERIVED,
        "container_uid": 101, "container_primary_gid": 101,
        "host_peer_uid": 200101, "host_peer_gid": 200101,
        "collector_allowed_uid": 200101, "collector_allowed_gid": 200101,
        "container_socket_group": "404", "host_socket_gid": 200404, "mapped_socket_gid": 200404}
    provenance = {"_type": "https://in-toto.io/Statement/v0.1",
        "predicateType": "https://slsa.dev/provenance/v0.2",
        "subject": [{"name": "pkg:docker/" + sd.ORIGIN_IMAGE + "@" + DERIVED + "?platform=linux%2Farm64", "digest": {"sha256": DERIVED[7:]}}],
        "predicate": {"buildType": "https://mobyproject.org/buildkit@v1",
            "invocation": {"configSource": {"uri": "https://github.com/rozkalnsandris/coloring-pages.git#" + sd.ORIGIN_RECIPE_SHA,
                "digest": {"sha1": sd.ORIGIN_RECIPE_SHA}, "entryPoint": "deploy/Dockerfile.origin-counting"},
                "parameters": {"args": {"build-arg:APPLICATION_IMAGE": "ghcr.io/" + sd.ORIGIN_REPOSITORY + "@" + BASE}}},
            "materials": [{"uri": "pkg:docker/ghcr.io/rozkalnsandris/coloring-pages@" + BASE + "?platform=linux%2Farm64",
                           "digest": {"sha256": BASE_PLATFORM[7:]}}]}}
    profile = {"schema": "rozkalns.coloring-pages.origin-profile.v1", "application_source_sha": SOURCE,
        "base_digest": BASE, "base_platform_digest": BASE_PLATFORM, "recipe_source_sha": sd.ORIGIN_RECIPE_SHA, "derivative_digest": DERIVED,
        "architecture": "linux/arm64", "socket_group": "404",
        "provenance_sha256": op.digest(provenance), "peer_evidence_sha256": op.digest(peer)}
    base = {"os": "linux", "architecture": "arm64", "config": {"Labels": {
        "org.opencontainers.image.revision": SOURCE,
        "io.rozkalns.simple-deploy.target": sd.ORIGIN_TARGET,
        "io.rozkalns.simple-deploy.shared-revision": TARGET["shared_workflow_sha"]}}}
    derived = copy.deepcopy(base)
    derived["config"].update({"User": "101", "Entrypoint": ["nginx"],
        "Cmd": ["-c", "/etc/nginx/nginx-origin.conf", "-g", "daemon off;"]})
    derived["config"]["Labels"].update({"io.rozkalns.origin.base-digest": BASE,
        "io.rozkalns.origin.recipe-revision": sd.ORIGIN_RECIPE_SHA})
    return {"schema": "rozkalns.origin-preparation.v1", "rpi_source_sha": HOST_SOURCE,
        "registry_sha256": hashlib.sha256(REGISTRY).hexdigest(), "profile": profile, "base_manifest_raw": BASE_MANIFEST,
        "base_config": base, "derivative_config": derived, "provenance": provenance, "peer_evidence": peer}


def v1_fixture():
    """Minimal synthetic analogue of the actual ARM64 BuildKit v1 wrapper.

    The OCI base material is the index digest; its unique ARM64 descriptor is
    checked separately by prepare() against the canonical base manifest.
    """
    request = fixture()
    statement = request["provenance"]
    statement["_type"] = "https://in-toto.io/Statement/v1"
    statement["predicate"]["materials"] = [
        {"uri": "pkg:docker/ghcr.io/rozkalnsandris/coloring-pages?digest=" + BASE +
                "&platform=linux%2Farm64", "digest": {"sha256": BASE[7:]}},
        {"uri": "https://github.com/rozkalnsandris/coloring-pages.git#" + sd.ORIGIN_RECIPE_SHA,
         "digest": {"sha1": sd.ORIGIN_RECIPE_SHA}},
    ]
    request["profile"]["provenance_sha256"] = op.digest(statement)
    return request


def prepare(value=None, **kwargs):
    return op.prepare(value or fixture(), REGISTRY, COMPOSE, source_sha=HOST_SOURCE, now=NOW, **kwargs)


class Runner:
    def __init__(self, request):
        self.request = request
        self.pointer = BASE
        self.calls = []
        self.fail_pull = False

    def run(self, argv, *, timeout_seconds):
        self.calls.append(tuple(argv))
        if argv[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            ref = argv[4]
            if ref.endswith(":production"):
                assert ref == "ghcr.io/" + sd.ORIGIN_REPOSITORY + ":production"
                return sd.CommandResult(0, json.dumps({"digest": self.pointer}), "")
            if ref == sd.ORIGIN_IMAGE + "@" + self.request["profile"]["derivative_digest"]:
                return sd.CommandResult(0, json.dumps(self.request["derivative_config"]), "")
            if ref in {"ghcr.io/" + sd.ORIGIN_REPOSITORY + "@" + self.request["profile"][key] for key in ("base_digest", "base_platform_digest")}:
                return sd.CommandResult(0, json.dumps(self.request["base_config"]), "")
        if argv[:2] == ["docker", "compose"]:
            if "ps" in argv:
                return sd.CommandResult(0, "4" * 64, "")
            if "pull" in argv and self.fail_pull:
                return sd.CommandResult(1, "", "synthetic failure")
            return sd.CommandResult(0, "", "")
        if argv[:2] == ["docker", "inspect"]:
            return sd.CommandResult(0, sd.ORIGIN_IMAGE + "@" + self.request["profile"]["derivative_digest"], "")
        raise AssertionError(argv)


class Http:
    def get(self, url, *, timeout_seconds):
        return 200


class OriginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = fixture()
        self.bundle = prepare(self.request)
        self.runner = Runner(self.request)
        self.compose_root = self.root / "compose"
        self.compose_root.mkdir()
        self.compose = self.compose_root / "coloring-pages-origin.json.yml"
        self.compose.write_text(self.bundle["compose"])
        self.compose.chmod(0o600)
        self.registry_path = self.root / "targets.json"
        self.registry_path.write_text(json.dumps(self.bundle["registry"]))
        self.deployer = sd.SimpleDeployer(registry=sd.load_registry(self.registry_path),
            identity=sd.DeployerIdentity(HOST_SOURCE), state=sd.StateStore(self.root / "state"),
            runner=self.runner, http=Http(), compose_root=self.compose_root)

    def tearDown(self):
        self.temp.cleanup()

    def no_mutation(self):
        self.assertFalse(any(c[:2] == ("docker", "compose") for c in self.runner.calls))
        self.assertEqual(list(self.deployer.state.overrides.iterdir()), [])

    def test_defaults_and_unrelated_targets_unchanged(self):
        raw = json.loads(REGISTRY)
        original = sd.load_registry(ROOT / "ops/deploy/simple-deploy-targets-v1.json")
        self.assertTrue(all(t.origin_counting is None for t in original.targets))
        for a, b in zip(raw["targets"], self.bundle["registry"]["targets"]):
            if a["target_alias"] != sd.ORIGIN_TARGET:
                self.assertEqual(a, b)
            else:
                reduced = copy.deepcopy(b)
                del reduced["origin_counting"]
                reduced["compose"] = a["compose"]
                self.assertEqual(a, reduced)
        self.assertEqual(hashlib.sha256(COMPOSE).hexdigest(), sd.ORIGIN_BASE_COMPOSE_SHA256)
        self.assertNotIn(sd.ORIGIN_SOCKET, COMPOSE.decode())
        self.assertFalse(self.bundle["runtime_authority"])

    def test_only_four_service_fields_change(self):
        # Pin the source bytes; compare all non-variant fields to independent expected values.
        service = json.loads(self.bundle["compose"])["services"]["coloring-pages"]
        for key in ("image", "platform", "group_add"):
            service.pop(key)
        socket = service["volumes"].pop()
        self.assertEqual(socket, {"type": "bind", "source": sd.ORIGIN_SOCKET, "target": sd.ORIGIN_SOCKET,
                                "read_only": True, "bind": {"create_host_path": False}})
        self.assertEqual(service, {"ports": ["127.0.0.1:9191:8080"],
            "volumes": [{"type": "bind", "source": "/srv/coloring-pages-content/public",
                         "target": "/var/lib/coloring-pages/public", "read_only": True, "bind": {"create_host_path": False}}],
            "read_only": True, "tmpfs": ["/tmp"], "security_opt": ["no-new-privileges:true"], "cap_drop": ["ALL"],
            "healthcheck": {"test": ["CMD", "wget", "--quiet", "--output-document=-", "http://127.0.0.1:8080/ready"],
                            "interval": "30s", "timeout": "5s", "retries": 3, "start_period": "10s"},
            "restart": "unless-stopped"})

    def test_success_idempotency_and_exact_derivative(self):
        result = self.deployer.reconcile(sd.ORIGIN_TARGET)
        self.assertEqual((result.result, result.desired_digest), ("SUCCESS", DERIVED))
        override = json.loads(self.deployer.state.override_path(sd.ORIGIN_TARGET).read_text())
        self.assertEqual(override, {"services": {"coloring-pages": {"image": sd.ORIGIN_IMAGE + "@" + DERIVED}}})
        self.assertTrue(any(c[4] == "ghcr.io/" + sd.ORIGIN_REPOSITORY + "@" + BASE_PLATFORM
                            for c in self.runner.calls if c[:4] == ("docker", "buildx", "imagetools", "inspect")))
        receipt = self.deployer.state.last_success(self.deployer.registry.get(sd.ORIGIN_TARGET))
        self.assertEqual(receipt["pointer_digest_before"], BASE)
        self.assertFalse(receipt["pointer_changed_during_attempt"])
        self.assertEqual(receipt["origin_profile_sha256"], self.bundle["profile_sha256"])
        self.runner.calls.clear()
        self.assertEqual(self.deployer.reconcile(sd.ORIGIN_TARGET).result, "NO_OP_CURRENT")
        self.assertFalse(any(c[:2] == ("docker", "compose") for c in self.runner.calls))

    def test_new_default_pointer_holds_without_override_or_mutation(self):
        self.runner.pointer = NEW_BASE
        for _ in range(2):
            self.assertEqual(self.deployer.reconcile(sd.ORIGIN_TARGET).result, "HOLD_ORIGIN_PAIR_REQUIRED")
        self.no_mutation()
        self.assertIsNone(self.deployer.state.last_success(self.deployer.registry.get(sd.ORIGIN_TARGET)))
        self.assertEqual(self.deployer.state.last_status(sd.ORIGIN_TARGET)["error_code"], "REVIEWED_DERIVATIVE_REQUIRED")

    def test_profile_removal_cannot_fallback_after_prior_optin(self):
        self.deployer.reconcile(sd.ORIGIN_TARGET)
        original = sd.load_registry(ROOT / "ops/deploy/simple-deploy-targets-v1.json")
        self.deployer.registry = original
        (self.compose_root / "coloring-pages-public.yml").write_bytes(COMPOSE)
        (self.compose_root / "coloring-pages-public.yml").chmod(0o600)
        self.runner.calls.clear()
        with self.assertRaisesRegex(sd.SimpleDeployError, "ORIGIN_PROFILE_REMOVAL_FORBIDDEN"):
            self.deployer.reconcile(sd.ORIGIN_TARGET)
        self.assertFalse(any(c[:2] == ("docker", "compose") for c in self.runner.calls))

    def test_changed_profile_requires_reconcile_even_for_same_image(self):
        self.deployer.reconcile(sd.ORIGIN_TARGET)
        # Find by target identity, not registry ordering.
        entry = next(t for t in self.bundle["registry"]["targets"] if t["target_alias"] == sd.ORIGIN_TARGET)
        entry["origin_counting"]["socket_group"] = "405"
        updated = sd.render_origin_compose(entry["origin_counting"])
        self.compose.write_bytes(updated)
        entry["compose"]["file_sha256"] = hashlib.sha256(updated).hexdigest()
        self.registry_path.write_text(json.dumps(self.bundle["registry"]))
        self.deployer.registry = sd.load_registry(self.registry_path)
        self.assertEqual(self.deployer.reconcile(sd.ORIGIN_TARGET).result, "SUCCESS")

    def test_compose_drift_blocks_before_commands(self):
        self.compose.write_text(self.bundle["compose"] + " ")
        with self.assertRaisesRegex(sd.SimpleDeployError, "COMPOSE_CONTRACT_INVALID"):
            self.deployer.reconcile(sd.ORIGIN_TARGET)
        self.assertEqual(self.runner.calls, [])

    def test_bad_published_metadata_blocks_before_mutation(self):
        for side, key, value in [("derivative_config", "architecture", "amd64"), ("base_config", "architecture", "amd64")]:
            with self.subTest(side=side):
                self.runner.request = fixture()
                self.runner.request[side][key] = value
                with self.assertRaises(sd.SimpleDeployError):
                    self.deployer.reconcile(sd.ORIGIN_TARGET)
                self.no_mutation()
        for key in ("org.opencontainers.image.revision", "io.rozkalns.origin.base-digest", "io.rozkalns.origin.recipe-revision"):
            with self.subTest(key=key):
                self.runner.request = fixture()
                self.runner.request["derivative_config"]["config"]["Labels"][key] = "wrong"
                with self.assertRaises(sd.SimpleDeployError):
                    self.deployer.reconcile(sd.ORIGIN_TARGET)
                self.no_mutation()

    def test_post_mutation_failure_stays_blocked(self):
        self.runner.fail_pull = True
        with self.assertRaises(sd.SimpleDeployError):
            self.deployer.reconcile(sd.ORIGIN_TARGET)
        count = len(self.runner.calls)
        self.assertEqual(self.deployer.reconcile(sd.ORIGIN_TARGET).result, "BLOCKED_STOP_ERROR")
        self.assertEqual(len(self.runner.calls), count)

    def test_reviewed_next_pair_advances_without_default_fallback(self):
        self.deployer.reconcile(sd.ORIGIN_TARGET)
        updated = fixture()
        updated["profile"]["base_platform_digest"] = NEW_BASE
        updated["base_manifest_raw"] = BASE_MANIFEST.replace(BASE_PLATFORM, NEW_BASE)
        next_base = "sha256:" + hashlib.sha256(updated["base_manifest_raw"].encode()).hexdigest()
        next_derived = "sha256:" + "5" * 64
        updated["profile"].update(base_digest=next_base, derivative_digest=next_derived, application_source_sha="c" * 40)
        for key in ("base_config", "derivative_config"):
            updated[key]["config"]["Labels"]["org.opencontainers.image.revision"] = "c" * 40
        updated["derivative_config"]["config"]["Labels"]["io.rozkalns.origin.base-digest"] = next_base
        updated["peer_evidence"]["image_ref"] = sd.ORIGIN_IMAGE + "@" + next_derived
        provenance = updated["provenance"]
        provenance["subject"][0]["name"] = "pkg:docker/" + sd.ORIGIN_IMAGE + "@" + next_derived + "?platform=linux%2Farm64"
        provenance["subject"][0]["digest"]["sha256"] = next_derived[7:]
        provenance["predicate"]["invocation"]["parameters"]["args"]["build-arg:APPLICATION_IMAGE"] = "ghcr.io/" + sd.ORIGIN_REPOSITORY + "@" + next_base
        provenance["predicate"]["materials"][0].update(uri="pkg:docker/ghcr.io/rozkalnsandris/coloring-pages@" + next_base + "?platform=linux%2Farm64", digest={"sha256": NEW_BASE[7:]})
        updated["profile"]["provenance_sha256"] = op.digest(provenance)
        updated["profile"]["peer_evidence_sha256"] = op.digest(updated["peer_evidence"])
        bundle = prepare(updated)
        self.compose.write_text(bundle["compose"])
        self.registry_path.write_text(json.dumps(bundle["registry"]))
        self.deployer.registry = sd.load_registry(self.registry_path)
        self.runner.request = updated
        self.runner.pointer = next_base
        self.assertEqual(self.deployer.reconcile(sd.ORIGIN_TARGET).desired_digest, next_derived)
        receipt = self.deployer.state.last_success(self.deployer.registry.get(sd.ORIGIN_TARGET))
        self.assertEqual(receipt["image_ref"], sd.ORIGIN_IMAGE + "@" + next_derived)
        self.assertEqual(receipt["consumer_source_sha"], "c" * 40)
        self.assertEqual(self.deployer.reconcile(sd.ORIGIN_TARGET).result, "NO_OP_CURRENT")

    def test_hold_cli_is_not_success(self):
        self.runner.pointer = NEW_BASE
        with patch.object(sd, "_production_deployer", return_value=self.deployer), patch("builtins.print") as output:
            self.assertEqual(sd.main(["--target", sd.ORIGIN_TARGET]), 1)
            self.assertIn("HOLD_ORIGIN_PAIR_REQUIRED", output.call_args.args[0])
        self.no_mutation()

    def test_manifest_provenance_cannot_substitute_another_platform(self):
        for mutate in (
            lambda r: r.update(base_manifest_raw=BASE_MANIFEST + " "),
            lambda r: r["profile"].update(base_platform_digest=NEW_BASE),
            lambda r: r["provenance"]["subject"][0].update(name="pkg:docker/wrong@tag?platform=linux%2Farm64"),
            lambda r: r["provenance"]["predicate"]["invocation"]["configSource"].update(uri="https://github.com/rozkalnsandris/coloring-pages.git#main"),
        ):
            r = fixture()
            mutate(r)
            r["profile"]["provenance_sha256"] = op.digest(r["provenance"])
            with self.assertRaises(op.Refusal):
                prepare(r)

    def test_invalid_profiles(self):
        for key, value in [("socket_group", "0"), ("socket_group", "0404"), ("socket_group", "root"),
                ("socket_group", True), ("socket_group", "4294967295"), ("socket_group", "${GROUP}"),
                ("architecture", "linux/amd64"), ("recipe_source_sha", "c" * 40),
                ("base_digest", "production"), ("derivative_digest", BASE),
                ("derivative_digest", "sha256:" + "A" * 64), ("application_source_sha", "main"),
                ("provenance_sha256", "bad"), ("unknown", 1)]:
            with self.subTest(key=key, value=value):
                r = fixture()
                r["profile"][key] = value
                with self.assertRaises((op.Refusal, sd.SimpleDeployError)):
                    prepare(r)
        for value in (None, [], {}):
            with self.assertRaises(sd.SimpleDeployError):
                sd.validate_origin_profile(value)

    def test_real_buildkit_v1_wrapper_strict_index_material_and_legacy(self):
        modern = v1_fixture()
        modern_bundle = prepare(modern)
        self.assertEqual(modern_bundle["activation"], "NOT_PERFORMED")
        self.assertFalse(modern_bundle["runtime_authority"])
        self.assertEqual(prepare()["activation"], "NOT_PERFORMED")  # Legacy v0.1 still accepted.
        # Material ordering is not an identity or trust signal.
        modern["provenance"]["predicate"]["materials"].reverse()
        modern["profile"]["provenance_sha256"] = op.digest(modern["provenance"])
        self.assertEqual(prepare(modern)["activation"], "NOT_PERFORMED")

    def test_real_buildkit_v1_rehashed_provenance_drift_is_refused(self):
        changes = [
            lambda r: r["provenance"].update(_type="https://in-toto.io/Statement/v2"),
            lambda r: r["provenance"].update(_type="https://in-toto.io/Statement/v0.1"),
            lambda r: r["provenance"].update(predicateType="https://slsa.dev/provenance/v1"),
            lambda r: r["provenance"]["predicate"]["materials"][0].update(
                uri="pkg:docker/ghcr.io/rozkalnsandris/coloring-pages?digest=" + NEW_BASE +
                    "&platform=linux%2Farm64"),
            lambda r: r["provenance"]["predicate"]["materials"][0].update(
                uri="pkg:docker/ghcr.io/rozkalnsandris/coloring-pages?digest=" + BASE +
                    "&platform=linux%2Famd64"),
            lambda r: r["provenance"]["predicate"]["materials"][0].update(
                digest={"sha256": BASE_PLATFORM[7:]}),
            lambda r: r["provenance"]["predicate"]["materials"][0].update(
                uri="pkg:docker/ghcr.io/rozkalnsandris/coloring-pages@" + BASE +
                    "?platform=linux%2Farm64"),
            lambda r: r["provenance"]["predicate"]["materials"][1].update(
                uri="https://github.com/rozkalnsandris/coloring-pages.git#main"),
            lambda r: r["provenance"]["predicate"]["materials"][1].update(
                digest={"sha1": "f" * 40}),
            lambda r: r["provenance"]["predicate"]["materials"].append(
                copy.deepcopy(r["provenance"]["predicate"]["materials"][0])),
            lambda r: r["provenance"]["subject"][0].update(digest={"sha256": "f" * 64}),
            lambda r: r["provenance"]["predicate"]["invocation"]["configSource"].update(
                entryPoint="Dockerfile"),
            lambda r: r["provenance"]["predicate"]["invocation"]["parameters"]["args"].update(
                **{"build-arg:APPLICATION_IMAGE": "ghcr.io/other@sha256:" + "a" * 64}),
        ]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                request = v1_fixture()
                change(request)
                # Rehash the altered statement: hashes alone must not authorize it.
                request["profile"]["provenance_sha256"] = op.digest(request["provenance"])
                with self.assertRaises((op.Refusal, sd.SimpleDeployError)):
                    prepare(request)

    def test_real_buildkit_v1_index_is_bound_to_unique_arm64_manifest(self):
        request = v1_fixture()
        request["profile"]["base_platform_digest"] = NEW_BASE
        with self.assertRaises((op.Refusal, sd.SimpleDeployError)):
            prepare(request)

    def test_preparation_rejects_stale_mismatched_provenance_and_peer(self):
        mutations = [
            lambda r: r.update(rpi_source_sha="c" * 40),
            lambda r: r.update(registry_sha256="c" * 64),
            lambda r: r["base_config"].update(architecture="amd64"),
            lambda r: r["derivative_config"]["config"].update(User="0"),
            lambda r: r["derivative_config"]["config"].update(Cmd=["wrong"]),
            lambda r: r["provenance"]["subject"][0].update(digest={"sha256": "4" * 64}),
            lambda r: r["provenance"]["predicate"]["invocation"]["configSource"].update(digest={"sha1": "c" * 40}),
            lambda r: r["provenance"]["predicate"].update(materials=[]),
            lambda r: r["peer_evidence"].update(observed_at="2026-10-30T19:30:00Z"),
            lambda r: r["peer_evidence"].update(observed_at="2026-11-03T19:30:00Z"),
            lambda r: r["peer_evidence"].update(host_peer_uid=1),
            lambda r: r["peer_evidence"].update(mapped_socket_gid=404),
            lambda r: r["peer_evidence"].update(container_socket_group="405"),
            lambda r: r["peer_evidence"].update(image_ref=sd.ORIGIN_IMAGE + "@" + NEW_BASE),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(case=i):
                r = fixture()
                mutate(r)
                # Even a rehashed malformed receipt must fail semantic checks.
                r["profile"]["provenance_sha256"] = op.digest(r["provenance"])
                r["profile"]["peer_evidence_sha256"] = op.digest(r["peer_evidence"])
                with self.assertRaises((op.Refusal, sd.SimpleDeployError)):
                    prepare(r)

    def test_operator_no_host_network_subprocess_or_output_file(self):
        request = self.root / "request.json"
        request.write_text(json.dumps(self.request))
        argv = ["--request", str(request), "--request-sha256", hashlib.sha256(request.read_bytes()).hexdigest(),
                "--source-sha", HOST_SOURCE]
        with patch.object(op.os, "geteuid", return_value=1000), patch.object(op, "datetime") as clock, \
                patch.object(op.sd.subprocess, "run", side_effect=AssertionError("no subprocess")), \
                patch.object(op.sd.urllib_request, "urlopen", side_effect=AssertionError("no network")), \
                patch("builtins.print") as output:
            clock.now.return_value = NOW
            clock.strptime = datetime.strptime
            self.assertEqual(op.main(argv), 0)
            self.assertEqual(json.loads(output.call_args.args[0]), self.bundle)
        with patch.object(op.os, "geteuid", return_value=0), patch("builtins.print"):
            self.assertEqual(op.main(argv), 1)
        self.assertEqual(prepare(), prepare())

    def test_input_symlink_hash_and_duplicates_refused(self):
        path = self.root / "request.json"
        path.write_text(json.dumps(self.request))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        link = self.root / "link.json"
        link.symlink_to(path)
        with self.assertRaises(OSError):
            op.read_request(link, sha)
        with self.assertRaises(op.Refusal):
            op.read_request(path, "f" * 64)
        path.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(op.Refusal):
            op.read_request(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_target_and_adapter_mismatch_refused(self):
        for key, value in [("target_alias", "other"), ("image", sd.ORIGIN_IMAGE), ("architecture", "linux/amd64")]:
            raw = copy.deepcopy(self.bundle["registry"])
            entry = next(t for t in raw["targets"] if t["target_alias"] == sd.ORIGIN_TARGET)
            entry[key] = value
            self.registry_path.write_text(json.dumps(raw))
            with self.assertRaises(sd.SimpleDeployError):
                sd.load_registry(self.registry_path)
        raw = copy.deepcopy(self.bundle["registry"])
        entry = next(t for t in raw["targets"] if t["target_alias"] == sd.ORIGIN_TARGET)
        entry["compose"]["file_sha256"] = "0" * 64
        self.registry_path.write_text(json.dumps(raw))
        with self.assertRaises(sd.SimpleDeployError):
            sd.load_registry(self.registry_path)


if __name__ == "__main__":
    unittest.main()
