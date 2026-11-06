#!/usr/bin/env python3
"""Root-owned, one-shot, fail-closed GoatCounter SIMPLE diagnostic.

No secrets, credential loader, network CLI, installation or host operation is
performed by importing this module. Cloudflare GET requires a hash-pinned
GitHub owner capability with persistent replay protection; Collect keeps its
separate fail-closed grant/owner/read-only-mount boundary.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys

RELEASE_PREFIX = 'rpi5-goatcounter-simple-cloudflare-readonly-'
ROOT = Path(__file__).absolute().parent
ENTRY = ROOT / 'trusted_runner.py'
TRUSTED = ROOT / 'trusted-release.json'
GRANT = ROOT / 'owner-readonly-grant.json'  # NOT installed; COLLECT only.
DB = Path('/var/lib/ausmalwiese-goatcounter/goatcounter.sqlite3')
SHA = re.compile(r'[0-9a-f]{40}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
REPOSITORY = 'rozkalnsandris/RPi5_main'
SCOPE = 'GOATCOUNTER_SIMPLE_TRUSTED_READONLY_V1'
FILES = (
    'operator.py', 'cloudflare_rdc_operator.py',
    'ausmalwiese_goatcounter_tunnel_v1.py',
    'ausmalwiese_goatcounter_simple_route_v1.py',
    'ausmalwiese_goatcounter_simple_readiness_v1.py',
    'ausmalwiese_goatcounter_simple_evidence_v1.py',
    'ausmalwiese_goatcounter_simple_cloudflare_readback_v1.py',
    'ausmalwiese_goatcounter_simple_collect_readback_v1.py',
    'owner_capability.py',
    'trusted_runner.py',
)
OLD_FILES = FILES[:7]
_PROTECTED_CALL_CONSUMED = False


class Stop(Exception):
    pass


def require(condition):
    if not condition:
        raise Stop()


def safe_read(path, mode, maximum=196608):
    """Read only root-owned bounded regular file; no symlink traversal."""
    for parent in reversed(path.parents):
        s = parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0
                and s.st_gid == 0 and not (s.st_mode & 0o022))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_gid == 0
                and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == mode
                and 0 < s.st_size <= maximum)
        data = os.read(fd, maximum + 1)
        require(len(data) == s.st_size)
        return data
    finally:
        os.close(fd)


def load_json(path, mode):
    return json.loads(safe_read(path, mode, 8192).decode('utf-8'))


def verify_release(expected_source_sha):
    """Verify entire fixed package before loading executable dependencies."""
    require(type(expected_source_sha) is str and SHA.fullmatch(expected_source_sha))
    require(ROOT.parent == Path('/usr/local/libexec')
            and ROOT.name == RELEASE_PREFIX + expected_source_sha)
    require(os.geteuid() == 0 and Path(__file__).absolute() == ENTRY)
    release = load_json(TRUSTED, 0o400)
    require(type(release) is dict and set(release) ==
            {'schema', 'repository', 'source_sha', 'scope', 'sha256'})
    require(release['schema'] == 1 and release['repository'] == REPOSITORY
            and release['source_sha'] == expected_source_sha
            and release['scope'] == SCOPE and type(release['sha256']) is dict
            and set(release['sha256']) == set(FILES))
    for name in FILES:
        wanted = release['sha256'][name]
        require(type(wanted) is str and SHA256.fullmatch(wanted))
        data = safe_read(ROOT / name, 0o500 if name == 'trusted_runner.py' else 0o400)
        require(hashlib.sha256(data).hexdigest() == wanted)
    # Same release format expected by the already merged Cloudflare operator.
    old = load_json(ROOT / 'release.json', 0o400)
    require(type(old) is dict and set(old) ==
            {'schema', 'repository', 'source_sha', 'scope', 'sha256'})
    require(old['schema'] == 1 and old['repository'] == REPOSITORY
            and old['source_sha'] == expected_source_sha
            and old['scope'] == 'GOATCOUNTER_SIMPLE_CLOUDFLARE_READONLY'
            and type(old['sha256']) is dict
            and set(old['sha256']) == set(OLD_FILES)
            and all(old['sha256'][name] == release['sha256'][name]
                    for name in OLD_FILES))
    return True


def grant_ok(grant, *, scope, source_sha):
    """A file alone is not authorization; independent owner approval required."""
    return (type(grant) is dict
            and set(grant) == {'schema', 'repository', 'source_sha', 'scope',
                               'owner_approved', 'one_shot'}
            and grant['schema'] == 1 and grant['repository'] == REPOSITORY
            and grant['source_sha'] == source_sha and grant['scope'] == scope
            and grant['owner_approved'] is True and grant['one_shot'] is True)


def approved(scope, expected_source_sha, *, owner_gate=None):
    """COLLECT-only legacy gate; Cloudflare uses GitHub owner capability."""
    global _PROTECTED_CALL_CONSUMED
    require(scope == 'COLLECT')
    require(_PROTECTED_CALL_CONSUMED is False and callable(owner_gate))
    # Root-owned grant is only an additional fail-closed input; it is not
    # independent proof of an owner decision or durable one-shot consumption.
    require(grant_ok(load_json(GRANT, 0o400), scope=scope,
                     source_sha=expected_source_sha))
    _PROTECTED_CALL_CONSUMED = True  # Consume BEFORE external gate/any I/O.
    require(owner_gate(scope, expected_source_sha) is True)



def verified_import_path():
    """Isolated, no-bytecode imports; never shadow stdlib operator.py."""
    require(sys.flags.isolated == 1 and sys.flags.dont_write_bytecode == 1)
    require(str(ROOT) not in sys.path)
    # Python's own operator module must be cached BEFORE this trusted release
    # is temporarily made importable. A release file named operator.py must
    # never take the place of Python's standard-library operator.
    stdop = sys.modules.get('operator')
    require(stdop is not None and getattr(stdop, '__file__', None) is not None)
    require(Path(stdop.__file__).resolve()
            == Path(os.__file__).resolve().with_name('operator.py'))
    # No foreign preloaded dependency is allowed.
    for name in FILES[1:-1]:
        loaded = sys.modules.get(name[:-3])
        if loaded is not None:
            require(getattr(loaded, '__file__', None) is not None
                    and Path(loaded.__file__).absolute() == ROOT / name)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))


def release_import(name):
    """Only modules from the hash-verified fixed release may be imported."""
    require(name + '.py' in FILES[1:-1])
    module = importlib.import_module(name)
    require(getattr(module, '__file__', None) is not None
            and Path(module.__file__).absolute() == ROOT / (name + '.py'))
    return module


def offline_status(expected_source_sha):
    try:
        verify_release(expected_source_sha)
        return 'PASS_TRUSTED_SOURCE_ONLY'
    except Exception:
        return 'STOP_RELEASE'


def collect_once(*, expected_source_sha, owner_gate=None, readonly_proof=None):
    """Optional: no live WAL read without two independent runtime gates.

    The trusted caller must independently prove a non-bypassable RO mount
    namespace (including -shm) before returning True from readonly_proof.
    Neither a self-signed boolean nor statvfs alone is authority.
    """
    inserted = False
    try:
        verify_release(expected_source_sha)
        approved('COLLECT', expected_source_sha, owner_gate=owner_gate)
        require(callable(readonly_proof))
        require(readonly_proof((str(DB), str(DB) + '-wal',
                                str(DB) + '-shm')) is True)
        require(hasattr(os, 'ST_RDONLY'))
        require(DB.parent.stat().st_dev == DB.stat().st_dev)
        for target in (DB, Path(str(DB) + '-wal'), Path(str(DB) + '-shm')):
            require((os.statvfs(target).f_flag & os.ST_RDONLY) != 0)
        verified_import_path()
        inserted = True
        collect = release_import('ausmalwiese_goatcounter_simple_collect_readback_v1')
        value = collect.read_once(DB)
        return value if value in ('COLLECT_DISABLED_1',
                                  'COLLECT_CANDIDATE_130') else 'STOP_COLLECT'
    except Exception:
        return 'STOP_COLLECT'
    finally:
        if inserted and str(ROOT) in sys.path:
            sys.path.remove(str(ROOT))


def github_owner_authorized(*, expected_source_sha, approval_comment_id,
                            account_id, zone_id):
    """Use only the hash-pinned GitHub owner capability from this release."""
    capability = release_import('owner_capability')
    return capability.authorize_once(
        expected_source_sha=expected_source_sha,
        comment_id=approval_comment_id,
        account_id=account_id,
        zone_id=zone_id,
    ) is True


def cloudflare_once(*, expected_source_sha, approval_comment_id=None,
                    client_factory=None, account_id=None, zone_id=None):
    """One independently owner-approved GET-only Cloudflare diagnostic.

    GitHub owner approval is authenticated and durably consumed BEFORE the
    client factory or any Cloudflare dependency can dispatch. The client
    itself still comes from a separately approved credential capability.
    """
    inserted = False
    try:
        verify_release(expected_source_sha)
        require(type(approval_comment_id) is int and approval_comment_id > 0)
        verified_import_path()
        inserted = True
        require(github_owner_authorized(
            expected_source_sha=expected_source_sha,
            approval_comment_id=approval_comment_id,
            account_id=account_id,
            zone_id=zone_id,
        ))
        require(callable(client_factory))

        for name in (
                'cloudflare_rdc_operator',
                'ausmalwiese_goatcounter_tunnel_v1',
                'ausmalwiese_goatcounter_simple_route_v1',
                'ausmalwiese_goatcounter_simple_readiness_v1',
                'ausmalwiese_goatcounter_simple_evidence_v1',
                'ausmalwiese_goatcounter_simple_cloudflare_readback_v1'):
            release_import(name)
        client_type = sys.modules['cloudflare_rdc_operator'].CloudflareClient
        client = client_factory(client_type)
        require(type(client) is client_type)

        spec = importlib.util.spec_from_file_location(
            'goatcounter_cloudflare_operator', ROOT / 'operator.py')
        require(spec is not None and spec.loader is not None)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        status, _ = module.run_guarded(client=client, account_id=account_id,
                                       zone_id=zone_id,
                                       expected_source_sha=expected_source_sha)
        return ('PASS_EDGE_SOURCE_ONLY' if status == 'PASS_EDGE_SOURCE_ONLY'
                else 'STOP_CLOUDFLARE')
    except Exception:
        return 'STOP_CLOUDFLARE'
    finally:
        if inserted and str(ROOT) in sys.path:
            sys.path.remove(str(ROOT))


if __name__ == '__main__':
    # Source-check CLI only; protected readers are only callable by trusted
    # separately owner-authorized code, and never through shell arguments.
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-check', action='store_true', required=True)
    parser.add_argument('--expected-source-sha', required=True)
    args = parser.parse_args()
    status = offline_status(args.expected_source_sha)
    print(status)
    raise SystemExit(0 if status == 'PASS_TRUSTED_SOURCE_ONLY' else 2)
