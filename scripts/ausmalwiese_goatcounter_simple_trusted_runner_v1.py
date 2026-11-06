#!/usr/bin/env python3
"""Root-owned, one-shot, fail-closed GoatCounter SIMPLE diagnostic (source only).

No secrets, credential loader, network CLI, installation or host operation is
performed by importing this module. Protected modes require a separately
owner-authorized, independently provisioned root-owned grant and caller.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path('/usr/local/libexec/rpi5-goatcounter-simple-cloudflare-readonly')
ENTRY = ROOT / 'trusted_runner.py'
TRUSTED = ROOT / 'trusted-release.json'
GRANT = ROOT / 'owner-readonly-grant.json'  # NOT installed; separate owner gate.
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


def approved(scope, expected_source_sha):
    global _PROTECTED_CALL_CONSUMED
    require(scope in ('COLLECT', 'CLOUDFLARE_GET'))
    require(_PROTECTED_CALL_CONSUMED is False)
    # Installer never places the grant. It can only be created under a distinct
    # exact owner gate, whose independent provenance the caller must verify.
    require(grant_ok(load_json(GRANT, 0o400), scope=scope,
                     source_sha=expected_source_sha))
    _PROTECTED_CALL_CONSUMED = True  # BEFORE first protected read/GET



def verified_import_path():
    # A caller must not pre-load checkout/foreign modules before verification.
    # Check cache BEFORE any imported module can execute in a protected mode.
    for name in FILES[1:-1]:
        loaded = sys.modules.get(name[:-3])
        if loaded is not None:
            require(getattr(loaded, '__file__', None) is not None
                    and Path(loaded.__file__).absolute() == ROOT / name)
    sys.dont_write_bytecode = True
    if str(ROOT) in sys.path:
        sys.path.remove(str(ROOT))
    sys.path.insert(0, str(ROOT))


def offline_status(expected_source_sha):
    try:
        verify_release(expected_source_sha)
        return 'PASS_TRUSTED_SOURCE_ONLY'
    except Exception:
        return 'STOP_RELEASE'


def collect_once(*, expected_source_sha):
    """No database open unless root-owned owner-grant AND kernel RO mount."""
    try:
        verify_release(expected_source_sha)
        approved('COLLECT', expected_source_sha)
        # Require an independently installed, approved read-only bind mount
        # that covers the *actual* DB and sidecar paths. No mount is created.
        require(hasattr(os, 'ST_RDONLY'))
        require(DB.parent.stat().st_dev == DB.stat().st_dev)
        for target in (DB, Path(str(DB) + '-wal'), Path(str(DB) + '-shm')):
            require((os.statvfs(target).f_flag & os.ST_RDONLY) != 0)
        # No checkout imports; modules are verified first and from fixed root.
        verified_import_path()
        import ausmalwiese_goatcounter_simple_collect_readback_v1 as collect
        require(Path(collect.__file__).absolute() == ROOT / (
            'ausmalwiese_goatcounter_simple_collect_readback_v1.py'))
        value = collect.read_once(DB)
        return value if value in ('COLLECT_DISABLED_1',
                                  'COLLECT_CANDIDATE_130') else 'STOP_COLLECT'
    except Exception:
        return 'STOP_COLLECT'


def cloudflare_once(*, expected_source_sha, client, account_id, zone_id):
    """Only a separately authorized trusted caller can supply credentials.

    Existing operator itself enforces exact host release, account binding,
    read-only GET allowlist, one GET per endpoint, no retries or redirects.
    No token/file opener is created here.
    """
    try:
        verify_release(expected_source_sha)
        approved('CLOUDFLARE_GET', expected_source_sha)
        verified_import_path()
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'goatcounter_cloudflare_operator', ROOT / 'operator.py')
        require(spec is not None and spec.loader is not None)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        status, summary = module.run_guarded(client=client, account_id=account_id,
                                            zone_id=zone_id,
                                            expected_source_sha=expected_source_sha)
        # Expose no raw Cloudflare data, even though underlying sanitizer only
        # returns an allowlisted summary.
        return 'PASS_EDGE_SOURCE_ONLY' if status == 'PASS_EDGE_SOURCE_ONLY' else 'STOP_CLOUDFLARE'
    except Exception:
        return 'STOP_CLOUDFLARE'


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
