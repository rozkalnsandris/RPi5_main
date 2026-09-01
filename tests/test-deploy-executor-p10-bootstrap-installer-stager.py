#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/install-deploy-executor-p10-bootstrap-installer-stager.py'
SERVICE_UNIT = ROOT / 'ops/systemd/rozkalns-deploy-executor.service'
loader = importlib.machinery.SourceFileLoader('p10_installer_stager', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)


def manifest_for(files: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    entries = [
        {'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        for path, data in sorted(files)
    ]
    core = {
        'schema': module.MANIFEST_SCHEMA,
        'sourceSha': module.DASHBOARD_SOURCE_SHA,
        'releasePath': f'/opt/dashboard_RPi5/releases/{module.DASHBOARD_SOURCE_SHA}',
        'nodeMajor': 24,
        'hashAlgorithm': 'sha256',
        'fileCount': len(entries),
        'totalBytes': sum(entry['bytes'] for entry in entries),
        'files': entries,
    }
    digest = hashlib.sha256(json.dumps(core, separators=(',', ':')).encode()).hexdigest()
    raw = json.dumps({**core, 'candidateSha256': digest}, separators=(',', ':')).encode()
    return raw, digest


class InstallerStagerContractTests(unittest.TestCase):
    def test_fixed_identities_and_no_path_cli(self) -> None:
        self.assertEqual(module.DASHBOARD_SOURCE_SHA, '5f7739348f56398d0ba301c9320e1de0062838fc')
        self.assertEqual(module.EXPECTED_CANDIDATE_SHA256, 'c5a2adef8f7242833094a1c0cb8a8074392312567deeddd1228dc46c16cff5c0')
        self.assertEqual(module.PRESERVED_PARENT_NAME, 'p10-preflight-5f773934-20260901T074158Z-294325')
        self.assertEqual(str(module.STAGING_PARENT), '/var/lib/rozkalns-dashboard-controller-bootstrap')
        self.assertEqual(str(module.STAGING_ROOT), f'/var/lib/rozkalns-dashboard-controller-bootstrap/{module.DASHBOARD_SOURCE_SHA}')
        self.assertNotIn('/var/lib/rozkalns-deploy-executor/bootstrap', str(module.STAGING_ROOT))
        args = module._parse_args(['0' * 40])
        self.assertFalse(args.apply)
        with self.assertRaises(SystemExit):
            module._parse_args(['0' * 40, '--candidate-root', '/tmp/x'])

    def test_trusted_target_blobs_are_frozen(self) -> None:
        self.assertEqual(len(module.TRUSTED_TARGETS), 4)
        self.assertEqual(module.INSTALLER_STAGER_MUTATION_BUDGET, (('fixed-staging-root-materialization', 1), ('trusted-entrypoint-installation', 1), ('trusted-module-installation', 3)))
        self.assertEqual(
            {target.expected_blob for target in module.TRUSTED_TARGETS},
            {
                'be46238c6bb7ed2aafef115db93830dc86a2ec44',
                'f446dfa5152531507312edcfcf66e8de5a73306d',
                'd258026312f9b9109c98b934e287d04a97fb8328',
                'b3e8d3995afb39820e64889a8f1b770fbcf70615',
            },
        )

    def test_state_directory_remains_separate_from_privileged_staging(self) -> None:
        unit = SERVICE_UNIT.read_text(encoding='utf-8')
        for required in (
            'User=rozkalns-deploy-executor',
            'Group=rozkalns-deploy-executor',
            'StateDirectory=rozkalns-deploy-executor',
            'StateDirectoryMode=0700',
            'ReadWritePaths=/var/lib/rozkalns-deploy-executor',
        ):
            self.assertIn(required, unit)
        self.assertNotIn('/var/lib/rozkalns-dashboard-controller-bootstrap', unit)
        self.assertNotIn('/var/lib/rozkalns-deploy-executor/bootstrap', SCRIPT.read_text(encoding='utf-8'))

    def test_manifest_requires_exact_digest(self) -> None:
        controller = b'test-controller'
        raw, digest = manifest_for([(module.CONTROLLER_RELATIVE_PATH, controller)])
        parsed = module._parse_manifest(raw, expected_digest=digest)
        self.assertEqual(parsed.candidate_sha256, digest)
        with self.assertRaises(module.InstallerStagerError):
            module._parse_manifest(raw, expected_digest='0' * 64)

    def test_candidate_verification_is_descriptor_safe_and_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = b'test-controller'
            other = b'abc123'
            for rel, data in [(module.CONTROLLER_RELATIVE_PATH, controller), ('apps/web/dist/index.html', other)]:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            raw, digest = manifest_for([
                (module.CONTROLLER_RELATIVE_PATH, controller),
                ('apps/web/dist/index.html', other),
            ])
            parsed = module._parse_manifest(raw, expected_digest=digest)
            old = module.HARDENED_CONTROLLER_BLOB
            try:
                module.HARDENED_CONTROLLER_BLOB = module._git_blob(controller)
                root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    module._verify_candidate(root_fd, parsed)
                    (root / 'apps/web/dist/index.html').write_bytes(b'changed')
                    with self.assertRaises(module.InstallerStagerError):
                        module._verify_candidate(root_fd, parsed)
                finally:
                    os.close(root_fd)
            finally:
                module.HARDENED_CONTROLLER_BLOB = old

    def test_source_has_no_generic_privileged_execution_surface(self) -> None:
        source = SCRIPT.read_text()
        self.assertNotIn('shell=True', source)
        self.assertNotIn('os.system(', source)
        self.assertNotIn('shutil.copy', source)
        self.assertNotIn('rsync', source)
        self.assertNotIn('sudo', source)
        self.assertNotIn('--command', source)
        self.assertNotIn('--script', source)
        self.assertNotIn('--production-root', source)
        self.assertIn("'PRODUCTION_RELEASES_MATERIALIZED=0'", source)
        self.assertIn("'CURRENT_POINTER_SWAPS=0'", source)
        self.assertIn("'P10_APPLY_EXECUTED=0'", source)
        self.assertNotIn('subprocess.run([', source.replace("[str(GIT), '-C', str(ROOT), *args]", ''))


if __name__ == '__main__':
    unittest.main(verbosity=2)
