#!/usr/bin/env python3
"""Source-only implementation of a one-shot exact-SHA trusted release installer.

NO installation is authorized by this file or its GitHub merge. Never install
without a separate owner order binding host, source SHA, target and permissions.
No overwrite/rollback/cleanup/retry behavior exists.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess

REPO = Path('/home/andris/RPi5_main')
ROOT = Path('/usr/local/libexec/rpi5-goatcounter-simple-cloudflare-readonly')
REPOSITORY = 'rozkalnsandris/RPi5_main'
SCOPE = 'GOATCOUNTER_SIMPLE_TRUSTED_READONLY_V1'
SHA = re.compile(r'[0-9a-f]{40}\Z')
SOURCE = {
    'operator.py': 'scripts/ausmalwiese_goatcounter_simple_cloudflare_operator_v1.py',
    'cloudflare_rdc_operator.py': 'scripts/cloudflare_rdc_operator.py',
    'ausmalwiese_goatcounter_tunnel_v1.py': 'scripts/ausmalwiese_goatcounter_tunnel_v1.py',
    'ausmalwiese_goatcounter_simple_route_v1.py': 'scripts/ausmalwiese_goatcounter_simple_route_v1.py',
    'ausmalwiese_goatcounter_simple_readiness_v1.py': 'scripts/ausmalwiese_goatcounter_simple_readiness_v1.py',
    'ausmalwiese_goatcounter_simple_evidence_v1.py': 'scripts/ausmalwiese_goatcounter_simple_evidence_v1.py',
    'ausmalwiese_goatcounter_simple_cloudflare_readback_v1.py':
        'scripts/ausmalwiese_goatcounter_simple_cloudflare_readback_v1.py',
    'ausmalwiese_goatcounter_simple_collect_readback_v1.py':
        'scripts/ausmalwiese_goatcounter_simple_collect_readback_v1.py',
    'trusted_runner.py': 'scripts/ausmalwiese_goatcounter_simple_trusted_runner_v1.py',
}
LEGACY_FILES = tuple(SOURCE)[:7]
CONFIRM = 'INSTALL-GOATCOUNTER-SIMPLE-READONLY-EXACT-SHA'


class Stop(Exception):
    pass


def require(ok):
    if not ok:
        raise Stop()


def git(*args):
    p = subprocess.run(['/usr/bin/git', '-C', str(REPO), *args],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=15,
                       env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    require(p.returncode == 0 and len(p.stdout) < 2000000)
    return p.stdout


def verify_checkout(sha):
    require(type(sha) is str and SHA.fullmatch(sha))
    require(REPO.is_dir() and not REPO.is_symlink())
    require(git('rev-parse', 'HEAD').decode().strip() == sha)
    require(git('branch', '--show-current').decode().strip() == 'main')
    require(git('remote', 'get-url', 'origin').decode().strip() ==
            'https://github.com/rozkalnsandris/RPi5_main.git')
    require(not git('status', '--porcelain=v1', '--untracked-files=all'))
    return True


def build_package(sha, blobs):
    """Pure exact input plan; this function performs no I/O or writes."""
    require(type(sha) is str and SHA.fullmatch(sha))
    require(type(blobs) is dict and set(blobs) == set(SOURCE))
    for value in blobs.values():
        require(type(value) is bytes and 0 < len(value) <= 196608)
    hashes = {name: hashlib.sha256(blobs[name]).hexdigest() for name in SOURCE}
    legacy = dict(schema=1, repository=REPOSITORY, source_sha=sha,
                  scope='GOATCOUNTER_SIMPLE_CLOUDFLARE_READONLY',
                  sha256={name: hashes[name] for name in LEGACY_FILES})
    trusted = dict(schema=1, repository=REPOSITORY, source_sha=sha,
                   scope=SCOPE, sha256=hashes)
    return {**{key: blobs[key] for key in SOURCE},
            'release.json': json.dumps(legacy, sort_keys=True,
                                       separators=(',', ':')).encode(),
            'trusted-release.json': json.dumps(trusted, sort_keys=True,
                                               separators=(',', ':')).encode()}


def load_checkout(sha):
    verify_checkout(sha)
    values = {}
    for name, path in SOURCE.items():
        f = REPO / path
        s = f.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1
                and not s.st_mode & 0o022)
        blob = f.read_bytes()
        require(blob == git('show', sha + ':' + path))
        values[name] = blob
    return build_package(sha, values)


def _root_safe(p):
    st = p.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0
            and st.st_gid == 0 and not (st.st_mode & 0o022))


def install_once(files):
    """ONE mutation sequence; first mkdir consumes separate LIVE approval.

    If any later error occurs, leave partial files untouched and STOP.
    Caller must independently prove owner authorization before invoking.
    """
    require(type(files) is dict and set(files) == set(SOURCE) | {
            'release.json', 'trusted-release.json'})
    for parent in reversed(ROOT.parents):
        _root_safe(parent)
    require(not os.path.lexists(ROOT))
    os.umask(0o077)
    os.mkdir(ROOT, 0o700)  # FIRST LIVE MUTATION if separately authorized.
    rootfd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in [*SOURCE, 'release.json', 'trusted-release.json']:
            require('/' not in name and name not in ('.', '..'))
            value = files[name]
            require(type(value) is bytes and 0 < len(value) <= 196608)
            mode = 0o500 if name == 'trusted_runner.py' else 0o400
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=rootfd)
            try:
                view = memoryview(value)
                while view:
                    n = os.write(fd, view)
                    require(n > 0)
                    view = view[n:]
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(rootfd)
    finally:
        os.close(rootfd)
    return 'INSTALLED_UNVERIFIED_RUNTIME'  # no runtime proof yet


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-main', required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--confirm-install')
    args = p.parse_args(argv)
    try:
        require(args.confirm_install is None if not args.apply else
                args.confirm_install == CONFIRM)
        require(type(args.expected_main) is str and SHA.fullmatch(args.expected_main))
        if args.apply:
            require(os.geteuid() == 0 and socket.gethostname() == 'rpi5')
        package = load_checkout(args.expected_main)
        if not args.apply:
            print('PASS_SOURCE_PLAN_ONLY')
            return 0
        print(install_once(package))
        return 0
    except Exception:
        print('STOP_INSTALL_UNCERTAIN')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
