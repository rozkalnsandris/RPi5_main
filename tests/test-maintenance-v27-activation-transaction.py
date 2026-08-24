#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops/bin/rpi5-maintenance-v27-activate"
LOCK_LIB = ROOT / "ops/lib/rpi5-maintenance-locks.sh"


def bash(script: str, *args: str, env: dict[str, str] | None = None) -> None:
    e = os.environ.copy()
    if env:
        e.update(env)
    p = subprocess.run(
        ["bash", "-c", script, "bash", *args],
        cwd=ROOT,
        env=e,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert p.returncode == 0, f"rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}"


with tempfile.TemporaryDirectory(prefix="rpi5-v27-activation-") as td:
    tmp = Path(td)

    bash(
        r'''
source "$1"
source "$2"
root="$3"; mkdir -p "$root"; update="$root/update.lock"; backup="$root/backup.lock"; shared="$root/shared.lock"
acquire_quiescent_window "$update" "$backup" "$shared"
[[ -n "$QUIESCENT_UPDATE_FD" && -n "$QUIESCENT_BACKUP_FD" && -n "$QUIESCENT_SHARED_FD" ]]
set +e
flock -xn -E 200 "$update" true; u=$?
flock -xn -E 200 "$backup" true; b=$?
flock -xn -E 200 "$shared" true; s=$?
set -e
[[ $u -eq 200 && $b -eq 200 && $s -eq 200 ]]
release_fd_var QUIESCENT_UPDATE_FD
flock -xn -E 200 "$update" true
set +e
flock -xn -E 200 "$backup" true; b=$?
flock -xn -E 200 "$shared" true; s=$?
set -e
[[ $b -eq 200 && $s -eq 200 ]]
acquire_quiescent_one updater "$update" QUIESCENT_UPDATE_FD
release_quiescent_window
flock -xn -E 200 "$update" true
flock -xn -E 200 "$backup" true
flock -xn -E 200 "$shared" true
''',
        str(LOCK_LIB), str(OPERATOR), str(tmp / "locks"),
    )

    tx = tmp / "tx"; tx.mkdir()
    for name, value in {
        "old-updater": "V26-old\n",
        "old-policy": "old-policy\n",
        "new-updater": "V27-new\n",
        "new-policy": "new-policy\n",
    }.items():
        (tx / name).write_text(value, encoding="utf-8")

    bash(
        r'''
source "$1"
r="$2"; ou="$r/old-updater"; op="$r/old-policy"; nu="$r/new-updater"; np="$r/new-policy"
du="$r/live-updater"; dp="$r/live-policy"
cp "$ou" "$du"; cp "$op" "$dp"

# Once mktemp succeeds, a later staging failure must leave the exact created
# path in the caller variable so STOP evidence can name the preserved artifact.
missing="$r/missing-source"; failed_stage=''
set +e
atomic_stage_copy "$missing" "$du" 0750 failed_stage; stage_rc=$?
set -e
[[ $stage_rc -ne 0 ]]
[[ -n "$failed_stage" && -f "$failed_stage" ]]
[[ "$failed_stage" == "$du".v27-stage.* ]]

# First replacement is atomic, and a stop between replacements preserves the
# exact partial state instead of silently rolling it back.
atomic_stage_copy "$np" "$dp" 0644 ps
atomic_stage_copy "$nu" "$du" 0750 us
atomic_replace_stage "$ps" "$dp"
cmp -s "$ou" "$du"; cmp -s "$np" "$dp"; [[ -f "$us" ]]

# A later authorized continuation can finish the already-reviewed second move.
atomic_replace_stage "$us" "$du"
cmp -s "$nu" "$du"; cmp -s "$np" "$dp"
''',
        str(OPERATOR), str(tx),
    )

    apt = tmp / "apt-lists"; apt.mkdir()
    (apt / "index").write_text("cached\n", encoding="utf-8")
    good = tmp / "good-check"
    good.write_text("#!/usr/bin/env bash\n[[ ${1:-} == --check ]] || exit 2\necho '--check: APT repozitoriju metadata netiks refreshēta'\n", encoding="utf-8")
    good.chmod(0o755)
    mutate = tmp / "mutate-check"
    mutate.write_text("#!/usr/bin/env bash\n[[ ${1:-} == --check ]] || exit 2\necho changed >> \"$FAKE_APT_ROOT/index\"\necho '--check: APT repozitoriju metadata netiks refreshēta'\n", encoding="utf-8")
    mutate.chmod(0o755)
    refresh = tmp / "refresh-check"
    refresh.write_text("#!/usr/bin/env bash\n[[ ${1:-} == --check ]] || exit 2\necho '--check: APT repozitoriju metadata netiks refreshēta'\necho 'APT repozitoriju metadatu atjaunināšana...'\n", encoding="utf-8")
    refresh.chmod(0o755)

    bash(
        r'''
source "$1"
good="$2"; mutate="$3"; refresh="$4"; apt="$5"; logs="$6"
verify_v27_check "$good" "$logs/good.log" "$apt"
[[ -n "$V27_APT_BEFORE" && "$V27_APT_BEFORE" == "$V27_APT_AFTER" ]]
set +e
verify_v27_check "$mutate" "$logs/mutate.log" "$apt"; m=$?
verify_v27_check "$refresh" "$logs/refresh.log" "$apt"; r=$?
set -e
[[ $m -ne 0 && $r -ne 0 ]]
''',
        str(OPERATOR), str(good), str(mutate), str(refresh), str(apt), str(tmp),
        env={"FAKE_APT_ROOT": str(apt)},
    )

print("Maintenance V27 activation dynamic transaction tests: PASS")
