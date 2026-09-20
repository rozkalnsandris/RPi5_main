#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SD_PATH = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"
spec = importlib.util.spec_from_file_location("simple_deploy_v1", SD_PATH)
assert spec and spec.loader
sd = importlib.util.module_from_spec(spec); sys.modules[spec.name] = sd; spec.loader.exec_module(sd)
SCHEMA_PATH = ROOT / "ops/lib/deploy_executor/simple_deploy_weather_schema_init_v1.py"
spec2 = importlib.util.spec_from_file_location("simple_deploy_weather_schema_init_v1", SCHEMA_PATH)
assert spec2 and spec2.loader
bridge = importlib.util.module_from_spec(spec2); sys.modules[spec2.name] = bridge; spec2.loader.exec_module(bridge)

DIGEST = "sha256:" + "1" * 64
SOURCE_SHA = bridge.EXPECTED_CONSUMER_SOURCE_SHA
SHARED_SHA = "e05ed760791a127c7c9628696806ef39c9fe329c"

class FakeHttp:
    def __init__(self, values): self.values=list(values); self.calls=[]
    def get(self, url, *, timeout_seconds):
        self.calls.append(url); return self.values.pop(0)

class FakeRunner:
    def __init__(self, *, pointer_after=DIGEST, fail_marker=None, volume=bridge.HOST_VOLUME, prior_container="", source_sha=SOURCE_SHA):
        self.calls=[]; self.pointer_calls=0; self.pointer_after=pointer_after; self.fail_marker=fail_marker; self.volume=volume; self.prior_container=prior_container; self.source_sha=source_sha
    def run(self, argv, *, timeout_seconds, stdin_text=None):
        call=tuple(argv); self.calls.append((call, stdin_text)); joined=" ".join(argv)
        if self.fail_marker and self.fail_marker in joined: return bridge.CommandResult(1,"","fail")
        if tuple(argv[:4]) == ("docker","buildx","imagetools","inspect"):
            ref=argv[4]
            if ref.endswith(":production"):
                self.pointer_calls += 1; digest = DIGEST if self.pointer_calls == 1 else self.pointer_after
                return bridge.CommandResult(0,json.dumps({"digest":digest})+"\n","")
            return bridge.CommandResult(0,json.dumps({"os":"linux","architecture":"arm64","config":{"Labels":{"org.opencontainers.image.revision":self.source_sha,"io.rozkalns.simple-deploy.target":bridge.TARGET_ALIAS,"io.rozkalns.simple-deploy.shared-revision":SHARED_SHA}}})+"\n","")
        if tuple(argv[:3]) == ("docker","volume","inspect"): return bridge.CommandResult(0,self.volume+"\n","")
        if tuple(argv[:3]) == ("docker","ps","-a"): return bridge.CommandResult(0,self.prior_container+"\n","")
        if tuple(argv[:2]) == ("docker","pull"): return bridge.CommandResult(0,"","")
        if tuple(argv[:2]) == ("docker","compose"): return bridge.CommandResult(0,"","")
        raise AssertionError(argv)

class Fixture:
    def __init__(self, runner=None, http=None):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.compose_root=self.root/"compose"; self.compose_root.mkdir()
        self.compose=self.compose_root/bridge.COMPOSE_FILE; self.compose.write_text((ROOT/"ops/deploy/simple-deploy-compose"/bridge.COMPOSE_FILE).read_text())
        digest=hashlib.sha256(self.compose.read_bytes()).hexdigest()
        payload=json.loads((ROOT/"ops/deploy/simple-deploy-targets-v1.json").read_text()); payload["targets"][0]["compose"]["file_sha256"]=digest
        self.registry=self.root/"targets.json"; self.registry.write_text(json.dumps(payload))
        self.identity=self.root/"identity.json"; self.identity.write_text(json.dumps({"schema":sd.IDENTITY_SCHEMA,"repository":sd.HOST_REPOSITORY,"source_sha":"b"*40}))
        self.runner=runner or FakeRunner(); self.http=http or FakeHttp([503,200])
        self.subject=bridge.WeatherSchemaInit(registry_path=self.registry,identity_path=self.identity,compose_root=self.compose_root,runner=self.runner,http=self.http)
    def close(self): self.tmp.cleanup()

class Tests(unittest.TestCase):
    def test_contract_and_installer_keep_schema_gate_separate(self):
        c=json.loads((ROOT/"ops/deploy/simple-deploy-weather-schema-init-v1.json").read_text())
        self.assertFalse(c["source_merge_authorizes_live"]); self.assertIn("ordinary-reconciliation-before-schema-ready",c["forbidden"]); self.assertEqual(c["consumer_source_sha"], bridge.EXPECTED_CONSUMER_SOURCE_SHA)
        install=json.loads((ROOT/"ops/deploy/simple-deploy-installer-v1.json").read_text())
        self.assertIn("database-or-data-mutation",install["not_performed_by_installer"])
        self.assertTrue(any(x.get("source")=="ops/bin/rozkalns-simple-deploy-weather-schema-init" for x in install["files"]))
    def test_pass_uses_immutable_digest_external_existing_volume_and_no_cleanup(self):
        fx=Fixture()
        try:
            r=fx.subject.apply(); self.assertEqual(r["result"],"PASS"); self.assertTrue(r["mutation_started"]); self.assertFalse(r["volume_create_delete_recreate"])
            calls=fx.runner.calls; self.assertTrue(any(c[0][:2]==("docker","pull") and DIGEST in c[0][2] for c in calls))
            compose=next(c for c in calls if c[0][:2]==("docker","compose")); self.assertIn("--pull",compose[0]); self.assertIn("never",compose[0]); self.assertNotIn("--rm",compose[0])
            override=json.loads(compose[1]); self.assertEqual(override["services"]["schema-init"]["image"],f"{bridge.IMAGE}@{DIGEST}"); self.assertEqual(override["volumes"]["weather_data"],{"external":True,"name":bridge.HOST_VOLUME})
        finally: fx.close()
    def test_ready_is_noop_before_any_docker_mutation(self):
        fx=Fixture(runner=FakeRunner(prior_container=bridge.SCHEMA_CONTAINER),http=FakeHttp([200]))
        try:
            r=fx.subject.apply(); self.assertEqual(r["result"],"NO_OP_ALREADY_READY"); self.assertFalse(r["mutation_started"]); self.assertFalse(any(c[0][:2] in (("docker","pull"),("docker","compose")) for c in fx.runner.calls)); self.assertFalse(any(c[0][:3] == ("docker","ps","-a") for c in fx.runner.calls))
        finally: fx.close()
    def test_missing_or_wrong_volume_fails_before_mutation(self):
        fx=Fixture(runner=FakeRunner(volume="wrong"),http=FakeHttp([503]))
        try:
            with self.assertRaisesRegex(bridge.SchemaInitError,"volume identity"): fx.subject.apply()
            self.assertFalse(any(c[0][:2] in (("docker","pull"),("docker","compose")) for c in fx.runner.calls))
        finally: fx.close()
    def test_prior_attempt_container_blocks_before_mutation(self):
        fx=Fixture(runner=FakeRunner(prior_container=bridge.SCHEMA_CONTAINER),http=FakeHttp([503]))
        try:
            with self.assertRaisesRegex(bridge.SchemaInitError,"evidence container"): fx.subject.apply()
            self.assertFalse(any(c[0][:2] == ("docker","pull") for c in fx.runner.calls))
        finally: fx.close()
    def test_unexpected_readiness_blocks_before_mutation(self):
        fx=Fixture(http=FakeHttp([500]))
        try:
            with self.assertRaisesRegex(bridge.SchemaInitError,"neither 200 nor expected 503"): fx.subject.apply()
            self.assertFalse(any(c[0][:2] == ("docker","pull") for c in fx.runner.calls))
        finally: fx.close()
    def test_wrong_consumer_source_sha_fails_before_mutation(self):
        fx=Fixture(runner=FakeRunner(source_sha="b"*40),http=FakeHttp([503]))
        try:
            with self.assertRaises(bridge.SchemaInitError) as cm: fx.subject.apply()
            self.assertEqual(cm.exception.code,"CONSUMER_SOURCE_DRIFT"); self.assertFalse(cm.exception.mutation_started)
            self.assertFalse(any(c[0][:2] in (("docker","pull"),("docker","compose")) for c in fx.runner.calls))
        finally: fx.close()
    def test_schema_failure_is_post_mutation_and_no_retry_cleanup(self):
        fx=Fixture(runner=FakeRunner(fail_marker=" schema-init"),http=FakeHttp([503]))
        try:
            with self.assertRaises(bridge.SchemaInitError) as cm: fx.subject.apply()
            self.assertTrue(cm.exception.mutation_started)
            compose=[c for c in fx.runner.calls if c[0][:2]==("docker","compose")]; self.assertEqual(len(compose),1); self.assertNotIn("--rm",compose[0][0])
        finally: fx.close()
    def test_pointer_change_after_schema_is_fail_closed_post_mutation(self):
        other="sha256:"+"2"*64; fx=Fixture(runner=FakeRunner(pointer_after=other),http=FakeHttp([503,200]))
        try:
            with self.assertRaises(bridge.SchemaInitError) as cm: fx.subject.apply()
            self.assertEqual(cm.exception.code,"POINTER_CHANGED"); self.assertTrue(cm.exception.mutation_started)
        finally: fx.close()
    def test_no_caller_arguments_or_arbitrary_authority_fields(self):
        source=SCHEMA_PATH.read_text(); wrapper=(ROOT/"ops/bin/rozkalns-simple-deploy-weather-schema-init").read_text()
        self.assertIn("if args:",source); self.assertNotIn("shell=True",source+wrapper); self.assertNotIn("os.system",source+wrapper)
        self.assertNotIn("rm ",source); self.assertNotIn("docker volume create",source); self.assertIn("/etc/rozkalns-simple-deployer/docker-anonymous",source)

if __name__ == "__main__": unittest.main()
