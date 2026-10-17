#!/usr/bin/env python3
"""One-shot Hermes prerequisite publication; separate exact LIVE authority required."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import ctypes
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import resource
import stat
import subprocess
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = 'scripts/prepare-hermes-state-adoption.py'
CONTRACT = 'ops/contracts/hermes-state-adoption-v1.json'
BASE = 'bcaa7c6db2d2404acb587d78a2dca7a0f7a1bb17'
REGISTRY_SOURCE = 'c53d5642a9b700c5c2a24df9382c45252bd443ab'
ORIGIN = 'https://github.com/rozkalnsandris/RPi5_main.git'
PRINCIPAL = 'rozkalns-simple-deployer'
ETC = Path('/etc/rozkalns-simple-deployer')
STATE = Path('/var/lib/rozkalns-simple-deployer')
EXECUTOR = Path('/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_v1.py')
ADAPTER = 'hermes-deals-household-api.yml'
LEGACY = 'hermes-deals-api.yml'
ENV = 'hermes-deals-api.env'
STATE_STAGE = '.hermes-deals-prerequisites-v2.staged'
ADAPTER_STAGE = '.hermes-deals-household-api.yml.adoption-v2.staged'
REGISTRY_STAGE = '.targets.json.hermes-adoption-v2.staged'
HISTORICAL_STATE_STAGE = '.hermes-deals-prerequisites-v1.staged'
HISTORICAL_ADAPTER_STAGE = '.hermes-deals-household-api.yml.adoption-v1.staged'
HISTORICAL_REGISTRY_STAGE = '.targets.json.hermes-adoption-v1.staged'
BASE_REGISTRY = 'ops/deploy/baselines/simple-deploy-targets-cv-stats-1000-v1.json'
NEW_REGISTRY = 'ops/deploy/simple-deploy-targets-v1.json'
ADAPTER_SOURCE = 'ops/deploy/simple-deploy-compose/' + ADAPTER
WEATHER_SOURCE = 'ops/deploy/simple-deploy-compose/rozkalns-weather-public.yml'
EXECUTOR_SOURCE = 'ops/lib/deploy_executor/simple_deploy_v1.py'
HASHES = {
    BASE_REGISTRY: '24e284a03f68c3843b629254ed1a944648e7b902ce36161a6ee7412cfe7c42d0',
    NEW_REGISTRY: 'fd804753594532ad2b6731428b4640c8f8b15758649e98c62259619cf4f90eca',
    ADAPTER_SOURCE: 'bc78b165b479b1dfcd7bcd12df28d09b649ca68f56d6bfdfa61be280f6e1dad3',
    WEATHER_SOURCE: 'eddbe28efd5270c350adcf18413839ed80d27d95387473cf7f4e2bf68584a04c',
    EXECUTOR_SOURCE: 'ed906786fd85169c6c555a3ac466b157edaf24a65fe12f60ee2ec6940ade20d0',
}
MAX_ENTRIES = 4096
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 4 * 1024 * 1024 * 1024
MAX_RAW_FILE = 128 * 1024 * 1024
STREAM_CHUNK = 64 * 1024
MAX_DEPTH = 12
STATIC_LIMIT = 128 * 1024
COLLECTOR_UID = 1000
COLLECTOR_GID = 1000
RAW_DEST_MODE = 0o3775
RAW_PLACEHOLDER = '.gitkeep'
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOATIME


class Stop(Exception):
    """Fixed code only; underlying exceptions and protected values are never emitted."""


def require(value):
    if not value:
        raise Stop()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ident(st):
    return st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode


def fingerprint(st):
    return (*ident(st), st.st_size, st.st_nlink, st.st_mtime_ns, st.st_ctime_ns)


def no_acl(fd):
    require(not {'system.posix_acl_access', 'system.posix_acl_default'} & set(os.listxattr(fd)))


@contextmanager
def directory(path, owners):
    require(path.is_absolute() and '..' not in path.parts)
    fd = os.open('/', DIR_FLAGS)
    try:
        for name in path.parts[1:]:
            st = os.fstat(fd)
            require(st.st_uid in owners and not st.st_mode & 0o022)
            no_acl(fd)
            child = os.open(name, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        require(os.fstat(fd).st_uid in owners and not os.fstat(fd).st_mode & 0o022)
        no_acl(fd)
        yield fd
    finally:
        os.close(fd)


def directory_meta(fd, uid, gid, mode):
    st = os.fstat(fd)
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == uid and st.st_gid == gid
            and stat.S_IMODE(st.st_mode) == mode)
    no_acl(fd)
    return ident(st)


def file_meta(st, uid, gid, mode):
    require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == uid
            and st.st_gid == gid and stat.S_IMODE(st.st_mode) == mode)


def absent(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    return False


def read_file(fd, name, uid, gid, mode, limit):
    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
    file_meta(before, uid, gid, mode)
    require(0 <= before.st_size <= limit)
    child = os.open(name, READ_FLAGS, dir_fd=fd)
    try:
        require(fingerprint(os.fstat(child)) == fingerprint(before))
        no_acl(child)
        value = bytearray()
        while True:
            part = os.read(child, min(65536, limit + 1 - len(value)))
            if not part:
                break
            value.extend(part)
            require(len(value) <= limit)
        require(len(value) == before.st_size)
        require(fingerprint(os.fstat(child)) == fingerprint(before))
        require(fingerprint(os.stat(name, dir_fd=fd, follow_symlinks=False)) == fingerprint(before))
        return bytes(value), fingerprint(before)
    finally:
        os.close(child)


def unique_json(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result)
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs)


class FileSnapshot(NamedTuple):
    """Bounded metadata only; root descriptors stay open for the entire apply."""
    root_fd: int
    root_fp: tuple
    parents: tuple
    name: str
    fp: tuple
    sha256: str

    @property
    def size(self):
        return self.fp[5]


def stream_file(fd, name, uid, gid, mode, limit, *, expected_fp=None, sink=None):
    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
    file_meta(before, uid, gid, mode)
    require(0 <= before.st_size <= limit)
    if expected_fp is not None:
        require(fingerprint(before) == expected_fp)
    child = os.open(name, READ_FLAGS, dir_fd=fd)
    try:
        require(fingerprint(os.fstat(child)) == fingerprint(before))
        no_acl(child)
        checksum = hashlib.sha256()
        length = 0
        while True:
            part = os.read(child, min(STREAM_CHUNK, before.st_size + 1 - length))
            if not part:
                break
            length += len(part)
            require(length <= before.st_size)
            checksum.update(part)
            if sink is not None:
                write_all(sink, part)
        require(length == before.st_size)
        require(fingerprint(os.fstat(child)) == fingerprint(before))
        require(fingerprint(os.stat(name, dir_fd=fd, follow_symlinks=False)) == fingerprint(before))
        return checksum.hexdigest(), fingerprint(before)
    finally:
        os.close(child)


@contextmanager
def source_parent(snapshot):
    """Reopen the recorded ancestry without following replaced directories."""
    with ExitStack() as stack:
        fd = snapshot.root_fd
        require(fingerprint(os.fstat(fd)) == snapshot.root_fp)
        no_acl(fd)
        opened = []
        for name, expected in snapshot.parents:
            require(fingerprint(os.stat(name, dir_fd=fd, follow_symlinks=False)) == expected)
            child = os.open(name, DIR_FLAGS | os.O_NOATIME, dir_fd=fd)
            stack.callback(os.close, child)
            require(fingerprint(os.fstat(child)) == expected)
            no_acl(child)
            opened.append((fd, name, child, expected))
            fd = child
        yield fd
        for parent, name, child, expected in reversed(opened):
            require(fingerprint(os.fstat(child)) == expected)
            require(fingerprint(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected)
        require(fingerprint(os.fstat(snapshot.root_fd)) == snapshot.root_fp)


def git(*args):
    return subprocess.run(
        ['/usr/bin/git', '--no-optional-locks', '-c', f'safe.directory={ROOT}',
         '-C', str(ROOT), *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=30, check=False, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                                     'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1'})


def git_bytes(*args):
    result = git(*args)
    require(result.returncode == 0)
    return result.stdout


def contract():
    return {
        'schema': 'hermes.state-adoption.v1', 'issue': 1014,
        'revision_issue': 1034, 'entrypoint': SCRIPT,
        'baseline_source': BASE, 'registry_baseline_source': REGISTRY_SOURCE,
        'source_hashes': HASHES,
        'source_trees': ['passwd(andris).home/hermes-deals/data/raw',
                         'passwd(andris).home/hermes-deals/config'],
        'destination': str(STATE / 'hermes-deals'),
        'staging': [str(STATE / STATE_STAGE), str(ETC / 'compose' / ADAPTER_STAGE),
                    str(ETC / REGISTRY_STAGE)],
        'historical_staging_evidence': [
            str(STATE / HISTORICAL_STATE_STAGE),
            str(ETC / 'compose' / HISTORICAL_ADAPTER_STAGE),
            str(ETC / HISTORICAL_REGISTRY_STAGE),
        ],
        'publish_order': ['state', 'adapter', 'registry'],
        'limits': {'entries': MAX_ENTRIES, 'file_bytes': MAX_FILE,
                   'raw_file_bytes': MAX_RAW_FILE,
                   'stream_chunk_bytes': STREAM_CHUNK,
                   'total_bytes': MAX_TOTAL, 'depth': MAX_DEPTH,
                   'static_file_bytes': STATIC_LIMIT},
        'identity_policy': 'strict schema and public ancestor of baseline; preserve bytes and inode',
        'existing_env': 'metadata only; preserve bytes, inode, owner, group, mode',
        'collector_identity': {'uid': COLLECTOR_UID, 'gid': COLLECTOR_GID},
        'raw_destination': 'root:collector-group directories 03775; root:root files 0644',
        'source_metadata': {
            'config': 'source-user-owned only',
            'raw_root': 'source-user-owned only',
            'raw_entries': 'source-user-owned or legacy root:root; legacy root directories 0755 and files 0644 only',
            'raw_placeholder': '.gitkeep only at raw root; regular zero-byte 0644',
        },
        'quiescence': 'generic and Hermes instance inactive; apply also requires collector/monitor services inactive and timers disabled',
        'default_data_content_read': False, 'default_mutation': False,
        'data_snapshot': 'metadata and SHA-256 only; bounded streaming copy and verification',
        'apply_requires_separate_live_authorization': True,
        'activation_eligible': False, 'retry': False, 'rollback': False, 'error_cleanup': False,
    }


def source_check(sha):
    require(re.fullmatch('[0-9a-f]{40}', sha) is not None)
    # Launch from a verified root-owned checkout; do not trust user-writable imports/Git config.
    with directory(ROOT, {0}):
        pass
    require(git_bytes('rev-parse', '--verify', 'HEAD').strip().decode() == sha)
    require(git_bytes('remote', 'get-url', 'origin').strip().decode() == ORIGIN)
    for args in (('diff-files', '--quiet', '--'), ('diff-index', '--cached', '--quiet', 'HEAD', '--')):
        require(git(*args).returncode == 0)
    require(not git_bytes('ls-files', '--others', '--exclude-standard'))
    require(git('merge-base', '--is-ancestor', BASE, sha).returncode == 0)
    require(git('merge-base', '--is-ancestor', REGISTRY_SOURCE, sha).returncode == 0)
    for relative in (SCRIPT, CONTRACT, *HASHES):
        raw = (ROOT / relative).read_bytes()
        require(git_bytes('show', f'{sha}:{relative}') == raw)
        if relative in HASHES:
            require(digest(raw) == HASHES[relative])
    require(unique_json((ROOT / CONTRACT).read_bytes()) == contract())
    registry_delta((ROOT / BASE_REGISTRY).read_bytes(), (ROOT / NEW_REGISTRY).read_bytes())


def registry_delta(old, new):
    require(digest(old) == HASHES[BASE_REGISTRY] and digest(new) == HASHES[NEW_REGISTRY])
    before, after = unique_json(old), unique_json(new)
    expected = unique_json(old)
    targets = [t for t in expected['targets'] if t['target_alias'] == 'hermes-deals']
    require(len(targets) == 1)
    targets[0]['compose']['file'] = ADAPTER
    targets[0]['compose']['file_sha256'] = HASHES[ADAPTER_SOURCE]
    require(after == expected and before != after)


def identity_provenance(raw):
    value = unique_json(raw)
    require(type(value) is dict and set(value) == {'schema', 'repository', 'source_sha'})
    require(value['schema'] == 'rozkalns.rpi5-main.simple-deploy.identity.v1'
            and value['repository'] == 'rozkalnsandris/RPi5_main')
    sha = value['source_sha']
    require(type(sha) is str and re.fullmatch('[0-9a-f]{40}', sha) is not None)
    # Provenance only, not a claim that all installed artifacts derive from this commit.
    # Missing history fails closed: fetch preparation is a separate explicit operation.
    require(git('merge-base', '--is-ancestor', sha, BASE).returncode == 0)


def runtime_ids():
    user, group = pwd.getpwnam(PRINCIPAL), grp.getgrnam(PRINCIPAL)
    require(user.pw_uid != 0 and user.pw_gid == group.gr_gid != 0)
    require(set(group.gr_mem) <= {PRINCIPAL})
    require({u.pw_name for u in pwd.getpwall() if u.pw_gid == group.gr_gid} == {PRINCIPAL})
    return user.pw_uid, group.gr_gid


def quiescent(apply=False):
    properties = ('LoadState', 'ActiveState', 'SubState', 'UnitFileState', 'Job', 'NeedDaemonReload')
    units = [(PRINCIPAL + instance + '.' + kind, kind, bool(instance))
             for instance in ('', '@hermes-deals') for kind in ('service', 'timer')]
    if apply:
        units.extend((f'hermes-deals-{name}.{kind}', kind, False)
                     for name in ('netto-collector', 'aldi-collector',
                                  'edeka-collector', 'edeka-monitor')
                     for kind in ('service', 'timer'))
    for unit, kind, allow_absent in units:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'show', unit, '--no-pager', '--all',
             *['--property=' + p for p in properties]],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
            check=False, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
        require(result.returncode == 0)
        values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines())
        require(set(values) == set(properties))
        require(values['ActiveState'] == 'inactive' and values['SubState'] == 'dead'
                and values['Job'] == '' and values['NeedDaemonReload'] == 'no')
        if allow_absent and values['LoadState'] == 'not-found':
            require(values['UnitFileState'] == '')
        else:
            require(values['LoadState'] == 'loaded')
            require(values['UnitFileState'] == ('disabled' if kind == 'timer' else 'static'))


def allowed_name(name, *, raw_root=False):
    # Fixed tree scope never reaches sibling .env/.git, keys, or database/backup artifacts.
    require((not name.startswith('.') or (raw_root and name == RAW_PLACEHOLDER))
            and len(os.fsencode(name)) <= 255)
    require(not name.lower().endswith(('.pem', '.key', '.db', '.sqlite', '.sqlite3', '.sql', '.bak')))


def source_owner(st, uid, gid, *, legacy_raw=False, nested=False):
    if (st.st_uid, st.st_gid) == (uid, gid):
        return
    require(legacy_raw and nested and (st.st_uid, st.st_gid) == (0, 0))
    if stat.S_ISDIR(st.st_mode):
        require(stat.S_IMODE(st.st_mode) == 0o755)
    else:
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                and stat.S_IMODE(st.st_mode) == 0o644)


def tree(fd, uid, gid, budget, *, depth=0, root_dev=None, file_limit=None,
         root_fd=None, root_fp=None, parents=(), legacy_raw=False):
    """Bounded descriptor walk; retain metadata/digests, never file contents."""
    require(depth <= MAX_DEPTH)
    file_limit = MAX_FILE if file_limit is None else file_limit
    before = os.fstat(fd)
    if root_fd is None:
        root_fd, root_fp = fd, fingerprint(before)
    source_owner(before, uid, gid, legacy_raw=legacy_raw, nested=bool(parents))
    require(stat.S_ISDIR(before.st_mode) and not before.st_mode & 0o7022)
    no_acl(fd)
    root_dev = before.st_dev if root_dev is None else root_dev
    require(before.st_dev == root_dev)
    entries = []
    with os.scandir(fd) as items:
        for item in items:
            budget[0] += 1
            require(budget[0] <= MAX_ENTRIES)
            allowed_name(item.name, raw_root=legacy_raw and not parents)
            entries.append(item.name)
    result = {}
    for name in sorted(entries):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require(st.st_dev == root_dev)
        source_owner(st, uid, gid, legacy_raw=legacy_raw, nested=True)
        if name == RAW_PLACEHOLDER:
            require(legacy_raw and not parents and stat.S_ISREG(st.st_mode)
                    and st.st_nlink == 1 and st.st_size == 0
                    and stat.S_IMODE(st.st_mode) == 0o644)
        if stat.S_ISDIR(st.st_mode):
            child = os.open(name, DIR_FLAGS | os.O_NOATIME, dir_fd=fd)
            try:
                require(fingerprint(os.fstat(child)) == fingerprint(st))
                nested = tree(child, uid, gid, budget, depth=depth + 1,
                              root_dev=root_dev, file_limit=file_limit,
                              root_fd=root_fd, root_fp=root_fp,
                              parents=(*parents, (name, fingerprint(st))),
                              legacy_raw=legacy_raw)
                require(fingerprint(os.stat(name, dir_fd=fd, follow_symlinks=False)) == fingerprint(st))
                result[name] = (fingerprint(st), nested)
            finally:
                os.close(child)
        else:
            require(stat.S_ISREG(st.st_mode) and not st.st_mode & 0o7133)
            require(0 <= st.st_size <= file_limit)
            budget[1] += st.st_size
            require(budget[1] <= MAX_TOTAL)
            # Reject growth after stat without allocating another file-sized budget.
            checksum, fp = stream_file(fd, name, st.st_uid, st.st_gid,
                                       stat.S_IMODE(st.st_mode), st.st_size,
                                       expected_fp=fingerprint(st))
            result[name] = (fp, FileSnapshot(root_fd, root_fp, parents, name, fp, checksum))
    require(fingerprint(os.fstat(fd)) == fingerprint(before))
    return result


def contents(snapshot):
    return {k: contents(v) if isinstance(v, dict) else v for k, (_, v) in snapshot.items()}


def write_all(fd, value):
    rest = memoryview(value)
    while rest:
        written = os.write(fd, rest)
        require(written > 0)
        rest = rest[written:]


def new_file(fd, name, value, mode, *, uid=0, gid=0):
    child = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600, dir_fd=fd)
    try:
        os.fchown(child, uid, gid)
        no_acl(child)
        if isinstance(value, FileSnapshot):
            with source_parent(value) as source:
                checksum, _ = stream_file(source, value.name, value.fp[2], value.fp[3],
                                          stat.S_IMODE(value.fp[4]), value.size,
                                          expected_fp=value.fp, sink=child)
                require(checksum == value.sha256)
        else:
            # Small public static artifacts; production data uses FileSnapshot.
            write_all(child, value)
        os.fchmod(child, mode)
        os.fsync(child)
        return fingerprint(os.fstat(child))
    finally:
        os.close(child)


@contextmanager
def new_directory(fd, name, *, uid=0, gid=0, mode=0o755):
    os.mkdir(name, 0o700, dir_fd=fd)
    child = os.open(name, DIR_FLAGS, dir_fd=fd)
    try:
        require(ident(os.stat(name, dir_fd=fd, follow_symlinks=False)) == ident(os.fstat(child)))
        os.fchown(child, uid, gid)
        os.fchmod(child, 0o700)
        directory_meta(child, uid, gid, 0o700)
        no_acl(child)
        yield child
        os.fchmod(child, mode)
        os.fsync(child)
    finally:
        os.close(child)


def raw_destination(path):
    return path[:2] == ('data', 'raw')


def write_tree(fd, data, *, uid=0, gid=0, collector_gid=COLLECTOR_GID, path=()):
    for name, value in data.items():
        if isinstance(value, dict):
            child_path = (*path, name)
            is_raw = raw_destination(child_path)
            with new_directory(fd, name, uid=uid,
                               gid=collector_gid if is_raw else gid,
                               mode=RAW_DEST_MODE if is_raw else 0o755) as child:
                write_tree(child, value, uid=uid, gid=gid,
                           collector_gid=collector_gid, path=child_path)
        else:
            new_file(fd, name, value, 0o644, uid=uid, gid=gid)


def verify_published_tree(fd, data, *, uid=0, gid=0,
                          collector_gid=COLLECTOR_GID, path=(), root_dev=None,
                          budget=None):
    """Verify the exact copied tree, including the collector-only raw directory mode."""
    require(len(path) <= MAX_DEPTH)
    budget = [0, 0] if budget is None else budget
    before = os.fstat(fd)
    is_raw = raw_destination(path)
    directory_meta(fd, uid, collector_gid if is_raw else gid,
                   RAW_DEST_MODE if is_raw else 0o755)
    root_dev = before.st_dev if root_dev is None else root_dev
    require(before.st_dev == root_dev)
    with os.scandir(fd) as entries:
        names = [entry.name for entry in entries]
    budget[0] += len(names)
    require(budget[0] <= MAX_ENTRIES)
    require(len(names) == len(data) and set(names) == set(data))
    raw_root = path == ('data', 'raw')
    for name in sorted(names):
        allowed_name(name, raw_root=raw_root)
        expected = data[name]
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require(st.st_dev == root_dev)
        if isinstance(expected, dict):
            require(stat.S_ISDIR(st.st_mode))
            with os_fd(name, fd, DIR_FLAGS | os.O_NOATIME) as child:
                require(fingerprint(os.fstat(child)) == fingerprint(st))
                verify_published_tree(child, expected, uid=uid, gid=gid,
                                      collector_gid=collector_gid, path=(*path, name),
                                      root_dev=root_dev, budget=budget)
                require(fingerprint(os.stat(name, dir_fd=fd,
                                            follow_symlinks=False)) == fingerprint(st))
        else:
            size = expected.size if isinstance(expected, FileSnapshot) else len(expected)
            checksum = expected.sha256 if isinstance(expected, FileSnapshot) else digest(expected)
            if name == RAW_PLACEHOLDER:
                require(raw_root and size == 0)
            require(0 <= st.st_size == size <= (MAX_RAW_FILE if is_raw else MAX_FILE))
            budget[1] += st.st_size
            require(budget[1] <= MAX_TOTAL)
            actual, _ = stream_file(fd, name, uid, gid, 0o644, size,
                                    expected_fp=fingerprint(st))
            require(actual == checksum)
    require(fingerprint(os.fstat(fd)) == fingerprint(before))


def rename_new(fd, stage, target):
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    require(rename(fd, stage.encode(), fd, target.encode(), 1) == 0)
    os.fsync(fd)


def publish(state, compose, etc, data, candidate, revalidate, receipt, *,
            uid=0, gid=0, collector_gid=COLLECTOR_GID):
    require(absent(state, STATE_STAGE) and absent(state, 'hermes-deals')
            and absent(compose, ADAPTER_STAGE) and absent(compose, ADAPTER)
            and absent(etc, REGISTRY_STAGE))
    revalidate()
    receipt['mutation_attempted'] = True
    with new_directory(state, STATE_STAGE, uid=uid, gid=gid) as stage:
        write_tree(stage, data, uid=uid, gid=gid, collector_gid=collector_gid)
    with os_fd(STATE_STAGE, state, DIR_FLAGS | os.O_NOATIME) as staged:
        verify_published_tree(staged, data, uid=uid, gid=gid, collector_gid=collector_gid)
        stage_fp = fingerprint(os.fstat(staged))
    adapter_fp = new_file(compose, ADAPTER_STAGE, candidate[ADAPTER_SOURCE], 0o444, uid=uid, gid=gid)
    registry_fp = new_file(etc, REGISTRY_STAGE, candidate[NEW_REGISTRY], 0o444, uid=uid, gid=gid)
    os.fsync(state)
    os.fsync(compose)
    os.fsync(etc)
    revalidate()
    require(fingerprint(os.stat(STATE_STAGE, dir_fd=state, follow_symlinks=False)) == stage_fp)
    rename_new(state, STATE_STAGE, 'hermes-deals')
    receipt['state_published'] = True

    def verify_state():
        with os_fd('hermes-deals', state, DIR_FLAGS | os.O_NOATIME) as target:
            require(ident(os.fstat(target)) == stage_fp[:5])
            verify_published_tree(target, data, uid=uid, gid=gid,
                                  collector_gid=collector_gid)

    revalidate()
    verify_state()
    require(fingerprint(os.stat(ADAPTER_STAGE, dir_fd=compose, follow_symlinks=False)) == adapter_fp)
    rename_new(compose, ADAPTER_STAGE, ADAPTER)
    receipt['adapter_published'] = True
    revalidate()
    verify_state()
    adapter_raw, adapter_final = read_file(compose, ADAPTER, uid, gid, 0o444, STATIC_LIMIT)
    require(adapter_raw == candidate[ADAPTER_SOURCE] and adapter_final[:5] == adapter_fp[:5])
    require(fingerprint(os.stat(REGISTRY_STAGE, dir_fd=etc, follow_symlinks=False)) == registry_fp)
    # Existing registry is the only replacement; its exact old bytes/inode are rechecked above.
    os.replace(REGISTRY_STAGE, 'targets.json', src_dir_fd=etc, dst_dir_fd=etc)
    receipt['registry_published'] = True
    os.fsync(etc)
    # Rename changes ctime, so compare content and inode separately.
    for fd, name, fp, relative in ((compose, ADAPTER, adapter_fp, ADAPTER_SOURCE),
                                  (etc, 'targets.json', registry_fp, NEW_REGISTRY)):
        raw, final = read_file(fd, name, uid, gid, 0o444, STATIC_LIMIT)
        require(raw == candidate[relative] and final[:5] == fp[:5])
    with os_fd('hermes-deals', state, DIR_FLAGS | os.O_NOATIME) as target:
        require(ident(os.fstat(target)) == stage_fp[:5])
        verify_published_tree(target, data, uid=uid, gid=gid,
                              collector_gid=collector_gid)


@contextmanager
def os_fd(name, fd, flags):
    child = os.open(name, flags, dir_fd=fd)
    try:
        yield child
    finally:
        os.close(child)


def execute(sha, apply, receipt):
    require(os.geteuid() == 0)
    source_check(sha)
    runtime = runtime_ids()
    source = pwd.getpwnam('andris')
    require(source.pw_uid == COLLECTOR_UID and source.pw_gid == COLLECTOR_GID)
    source_root = Path(source.pw_dir) / 'hermes-deals'
    paths = {'etc': (ETC, {0}, 0, 0, 0o755),
             'compose': (ETC / 'compose', {0}, 0, 0, 0o755),
             'private': (ETC / 'private', {0}, 0, runtime[1], 0o750),
             'state': (STATE, {0, runtime[0]}, *runtime, 0o700),
             'executor': (EXECUTOR.parent, {0}, 0, 0, 0o755),
             'raw': (source_root / 'data/raw', {0, source.pw_uid}, source.pw_uid, source.pw_gid, 0o755),
             'config': (source_root / 'config', {0, source.pw_uid}, source.pw_uid, source.pw_gid, 0o755)}
    with ExitStack() as stack:
        fds, initial = {}, {}
        for key, (path, owners, uid, gid, mode) in paths.items():
            fd = stack.enter_context(directory(path, owners))
            fds[key] = fd
            initial[key] = directory_meta(fd, uid, gid, mode)
        # No lock file created; these locks serialize this operator. Scheduler quiescence
        # is required separately; directory flocks are not generic-executor locks.
        for key in ('etc', 'state'):
            fcntl.flock(fds[key], fcntl.LOCK_EX | fcntl.LOCK_NB)
        candidate = {p: (ROOT / p).read_bytes() for p in HASHES}
        preserved = {}
        receipt['static_content_read'] = True
        for key, parent, name, relative in (
            ('registry', 'etc', 'targets.json', BASE_REGISTRY),
            ('identity', 'etc', 'identity.json', None),
            ('weather', 'compose', 'rozkalns-weather-public.yml', WEATHER_SOURCE),
            ('executor', 'executor', EXECUTOR.name, EXECUTOR_SOURCE),
        ):
            raw, fp = read_file(fds[parent], name, 0, 0, 0o444, STATIC_LIMIT)
            if relative:
                require(raw == candidate[relative])
            else:
                identity_provenance(raw)
            preserved[key] = (parent, name, raw, fp)
        env_before = os.stat(ENV, dir_fd=fds['private'], follow_symlinks=False)
        file_meta(env_before, 0, runtime[1], 0o640)
        # O_PATH pins metadata without reading/opening the protected contents.
        with os_fd(ENV, fds['private'], os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC) as env_fd:
            require(fingerprint(os.fstat(env_fd)) == fingerprint(env_before))
        # listxattr via proc descriptor isn't supported for O_PATH; use the trusted
        # fixed parent path, bounded by before/after inode fingerprint checks.
        require(not {'system.posix_acl_access', 'system.posix_acl_default'} &
                set(os.listxattr(ETC / 'private' / ENV, follow_symlinks=False)))
        require(fingerprint(os.stat(ENV, dir_fd=fds['private'], follow_symlinks=False)) == fingerprint(env_before))
        for key, name in (('state', STATE_STAGE), ('state', 'hermes-deals'),
                          ('compose', ADAPTER), ('compose', ADAPTER_STAGE),
                          ('etc', REGISTRY_STAGE)):
            require(absent(fds[key], name))

        def revalidate():
            source_check(sha)
            require(runtime_ids() == runtime)
            require(pwd.getpwnam('andris') == source)
            quiescent(apply)
            for key, (path, owners, uid, gid, mode) in paths.items():
                with directory(path, owners) as fresh:
                    require(directory_meta(fresh, uid, gid, mode) == initial[key])
                    require(ident(os.fstat(fds[key])) == initial[key])
            require(fingerprint(os.stat(ENV, dir_fd=fds['private'], follow_symlinks=False)) == fingerprint(env_before))
            for key, (parent, name, raw, fp) in preserved.items():
                if key == 'registry' and receipt['registry_published']:
                    current, _ = read_file(fds[parent], name, 0, 0, 0o444, STATIC_LIMIT)
                    require(current == candidate[NEW_REGISTRY])
                else:
                    require(read_file(fds[parent], name, 0, 0, 0o444, STATIC_LIMIT) == (raw, fp))
            for parent, name in (('compose', LEGACY), ('compose', '.hermes-deals-api.yml.adoption-v1.staged'),
                                 ('private', '.hermes-deals-api.env.child-v1.staged'),
                                 ('private', '.hermes-deals-api.env.prerequisites-v1.staged')):
                require(absent(fds[parent], name))
            if not receipt['state_published']:
                require(absent(fds['state'], 'hermes-deals'))
            if not receipt['adapter_published']:
                require(absent(fds['compose'], ADAPTER))

        revalidate()
        receipt['identity_provenance'] = 'PUBLIC_BASELINE_ANCESTOR_PRESERVED'
        if not apply:
            receipt['status'] = 'BASELINE_CHECKED_DATA_UNREAD'
            return
        receipt['data_content_read'] = True
        budget = [3, 0]  # destination's fixed data/raw/config directories count too
        snapshots = {key: tree(fds[key], source.pw_uid, source.pw_gid, budget,
                               depth=2 if key == 'raw' else 1,
                               file_limit=MAX_RAW_FILE if key == 'raw' else MAX_FILE,
                               legacy_raw=key == 'raw')
                     for key in ('raw', 'config')}
        source_fps = {key: fingerprint(os.fstat(fds[key])) for key in snapshots}
        data = {'data': {'raw': contents(snapshots['raw'])}, 'config': contents(snapshots['config'])}
        require(isinstance(data['config'].get('sources.json'), FileSnapshot)
                and data['config']['sources.json'].size > 0)

        def final_check():
            revalidate()
            budget = [3, 0]
            for key in snapshots:
                require(fingerprint(os.fstat(fds[key])) == source_fps[key])
                require(tree(fds[key], source.pw_uid, source.pw_gid, budget,
                             depth=2 if key == 'raw' else 1,
                             file_limit=MAX_RAW_FILE if key == 'raw' else MAX_FILE,
                             legacy_raw=key == 'raw') == snapshots[key])

        publish(fds['state'], fds['compose'], fds['etc'], data, candidate, final_check,
                receipt, collector_gid=COLLECTOR_GID)
        final_check()
        require(absent(fds['state'], STATE_STAGE) and absent(fds['compose'], ADAPTER_STAGE)
                and absent(fds['etc'], REGISTRY_STAGE))
        receipt['status'] = 'PREPARED_NO_ACTIVATION'


def new_receipt():
    return {'schema': 'hermes.state-adoption.result.v1', 'status': 'ERROR_STOP',
            'static_content_read': False, 'data_content_read': False, 'env_content_read': False,
            'protected_values_emitted': False, 'mutation_attempted': False,
            'state_published': False, 'adapter_published': False, 'registry_published': False,
            'identity_provenance': 'UNVERIFIED', 'activation_eligible': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    receipt = new_receipt()
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        execute(args.expected_source_sha, args.apply, receipt)
    except (Exception, KeyboardInterrupt):
        print(json.dumps(receipt, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())