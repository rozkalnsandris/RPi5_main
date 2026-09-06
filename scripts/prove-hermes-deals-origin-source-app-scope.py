#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ops' / 'lib'))

from deploy_executor.hermes_deals_origin_runtime_adapters import (  # noqa: E402
    ConcreteHermesDealsSourceAppScopeProver,
)
from deploy_executor.p9_source_auth import P9SourceTokenStageError  # noqa: E402

SHA_RE = re.compile(r'^[0-9a-f]{40}$')


class SourceAppScopeProofError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise SourceAppScopeProofError(message)


def _source_sha(expected_sha: str) -> None:
    if SHA_RE.fullmatch(expected_sha) is None:
        _fail('expected RPi5 source SHA is malformed')
    import subprocess
    result = subprocess.run(
        ('/usr/bin/git', 'rev-parse', 'HEAD'),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
    )
    if result.returncode != 0 or result.stdout.decode('ascii', 'strict').strip() != expected_sha:
        _fail('RPi5 checkout does not match expected source SHA')


def _receipt(result: str, expected_sha: str, **extra: object) -> str:
    value: dict[str, object] = {
        'schema': 'rozkalns.hermes-deals.origin-source-app-scope-proof-receipt.v1',
        'result': result,
        'source_sha': expected_sha,
        'credential_content_read': False,
        'github_api_request': False,
        'installation_token_minted': False,
        'installation_token_exposed': False,
        'credential_mutation': False,
        'filesystem_mutation': False,
        'systemd_mutation': False,
        'socket_request_sent': False,
        'helper_executed': False,
        'production_mutation_started': False,
    }
    value.update(extra)
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _public_proof(value: Any) -> Mapping[str, object]:
    return {
        'repository': value.repository,
        'repository_id': value.repository_id,
        'app_id': value.app_id,
        'installation_id': value.installation_id,
        'repository_selection': value.repository_selection,
        'token_repository_count': value.token_repository_count,
        'permissions': dict(value.permissions),
        'credential_content_read': value.credential_content_read,
        'github_api_request': value.github_api_request,
        'installation_token_minted': value.installation_token_minted,
        'installation_token_exposed': value.installation_token_exposed,
        'credential_mutation': value.credential_mutation,
        'filesystem_mutation': value.filesystem_mutation,
        'production_mutation_started': value.production_mutation_started,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Hermes Source App exact-scope protected proof gate',
    )
    parser.add_argument('expected_source_sha')
    parser.add_argument('--prove', action='store_true')
    args = parser.parse_args(argv)
    try:
        _source_sha(args.expected_source_sha)
        if not args.prove:
            print(_receipt('HERMES_SOURCE_APP_SCOPE_PROOF_PROTECTED_READY', args.expected_source_sha))
            return 0
        if os.geteuid() != 0:
            _fail('protected Source App scope proof requires root read context')
        proof = ConcreteHermesDealsSourceAppScopeProver().prove()
        public = dict(_public_proof(proof))
        print(
            _receipt(
                'HERMES_SOURCE_APP_SCOPE_PROVEN',
                args.expected_source_sha,
                **public,
            )
        )
        return 0
    except P9SourceTokenStageError as exc:
        print(
            _receipt(
                'FAIL_CLOSED',
                args.expected_source_sha,
                reason='source_app_scope_proof_failed',
                safe_stage=exc.stage,
            )
        )
        return 1
    except SourceAppScopeProofError:
        print(
            _receipt(
                'FAIL_CLOSED',
                args.expected_source_sha,
                reason='source_app_scope_proof_failed',
            )
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
