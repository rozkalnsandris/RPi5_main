#!/usr/bin/env python3
"""End-to-end regression for the V11 four-sample AdGuard series."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
COLLECTOR = REPO / "scripts/collect-adguard-memory-attribution.py"
SERIES = REPO / "scripts/collect-adguard-memory-series.py"
VERIFIER = REPO / "scripts/verify-adguard-memory-series.py"


def run(args: list[str], env: dict[str, str], *, success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=60,
    )
    if success and result.returncode:
        raise AssertionError(f"command failed: {args}\n{result.stdout}")
    if not success and result.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {args}\n{result.stdout}")
    return result


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_fixture(work: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    proc = work / "proc"
    cgroup = work / "cgroup"
    stub = work / "bin"
    process = proc / "123"
    fd = process / "fd"
    fd.mkdir(parents=True)
    for index in range(4):
        (fd / str(index)).touch()
    write(process / "comm", "AdGuardHome\n")
    write(
        process / "status",
        """Name:\tAdGuardHome
VmSize:\t700000 kB
VmRSS:\t450000 kB
RssAnon:\t420000 kB
RssFile:\t25000 kB
RssShmem:\t5000 kB
VmData:\t600000 kB
VmStk:\t132 kB
VmExe:\t12000 kB
VmLib:\t3000 kB
VmPTE:\t900 kB
VmSwap:\t16000 kB
Threads:\t15
""",
    )
    write(
        process / "smaps_rollup",
        """00400000-7fffffffffff ---p 00000000 00:00 0 [rollup]
Rss: 450000 kB
Pss: 430000 kB
Pss_Anon: 400000 kB
Pss_File: 25000 kB
Pss_Shmem: 5000 kB
Shared_Clean: 10000 kB
Shared_Dirty: 0 kB
Private_Clean: 15000 kB
Private_Dirty: 425000 kB
Anonymous: 420000 kB
AnonHugePages: 0 kB
Swap: 16000 kB
SwapPss: 8000 kB
Locked: 0 kB
""",
    )
    write(process / "cgroup", "0::/test.slice/adguard.scope\n")

    cg = cgroup / "test.slice/adguard.scope"
    cg.mkdir(parents=True)
    write(cg / "memory.current", f"{460000 * 1024}\n")
    write(cg / "memory.peak", f"{470000 * 1024}\n")
    write(cg / "memory.swap.current", f"{12000 * 1024}\n")
    write(cg / "memory.max", f"{500 * 1024 * 1024}\n")
    write(
        cg / "memory.stat",
        "\n".join(
            [
                f"anon {420000 * 1024}",
                f"file {20000 * 1024}",
                f"kernel {20000 * 1024}",
                f"kernel_stack {1000 * 1024}",
                f"pagetables {2000 * 1024}",
                "percpu 0",
                f"sock {2000 * 1024}",
                f"shmem {1000 * 1024}",
                f"file_mapped {5000 * 1024}",
                "file_dirty 0",
                "file_writeback 0",
                f"swapcached {100 * 1024}",
                f"slab_reclaimable {6000 * 1024}",
                f"slab_unreclaimable {4000 * 1024}",
                "workingset_refault_anon 12",
                "workingset_refault_file 34",
                "workingset_activate_anon 5",
                "workingset_activate_file 6",
                "pgfault 10000",
                "pgmajfault 70",
                "pgrefill 100",
                "pgscan 120",
                "pgsteal 110",
                "thp_fault_alloc 0",
            ]
        )
        + "\n",
    )
    write(cg / "memory.events", "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n")

    stub.mkdir()
    docker = stub / "docker"
    write(docker, "#!/usr/bin/env bash\nprintf 'adguard\\t438.4MiB / 500MiB\\t87.68%%\\t15\\n'\n")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    return proc, cgroup, stub


def main() -> None:
    evidence = REPO / "evidence"
    evidence.mkdir(exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="test-adguard-series.", dir=evidence))
    try:
        proc, cgroup, stub = build_fixture(work)
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{stub}:/usr/bin:/bin",
                "ADGUARD_ATTR_PROC_ROOT": str(proc),
                "ADGUARD_ATTR_CGROUP_ROOT": str(cgroup),
                "ADGUARD_ATTR_TEST_UID": "1000",
                "ADGUARD_ATTR_TEST_COMMIT": "a" * 40,
                "ADGUARD_ATTR_FIXED_UTC": "2026-08-07T06:00:00Z",
                "ADGUARD_ATTR_TEST_NO_SLEEP": "1",
            }
        )
        output = work / "series"
        result = run(
            ["python3", str(SERIES), "--output", str(output), "--interval-seconds", "0"],
            env,
        )
        assert "Stable dominant component: anonymous" in result.stdout
        run(["python3", str(VERIFIER), str(output)], env)

        series = json.loads((output / "series.json").read_text(encoding="utf-8"))
        assert series["schema"] == "rpi5.adguard-memory-series.v1"
        assert series["sample_count"] == 4
        assert series["git_commit"] == "a" * 40
        assert series["stable_dominant_component"] == "anonymous"
        assert series["container_usage_change_kib"] == 0
        assert series["max_container_percent_basis_points"] == 8768
        assert series["max_oom_kill"] == 0
        assert "stable_anonymous_dominance" in series["reason_codes"]
        assert [row["collected_at_utc"] for row in series["samples"]] == [
            "2026-08-07T06:00:00Z",
            "2026-08-07T06:00:01Z",
            "2026-08-07T06:00:02Z",
            "2026-08-07T06:00:03Z",
        ]

        unsafe_env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("ADGUARD_ATTR_")
        }
        unsafe_env["ADGUARD_ATTR_TEST_UID"] = "1000"
        unsafe = run(
            ["python3", str(COLLECTOR), "--output", str(work / "unsafe")],
            unsafe_env,
            success=False,
        )
        assert "test-only overrides require isolated fake proc/cgroup roots" in unsafe.stdout

        real_root_env = unsafe_env.copy()
        real_root_env["ADGUARD_ATTR_PROC_ROOT"] = "/proc"
        real_root_env["ADGUARD_ATTR_CGROUP_ROOT"] = "/sys/fs/cgroup"
        rejected = run(
            ["python3", str(COLLECTOR), "--output", str(work / "real-root")],
            real_root_env,
            success=False,
        )
        assert "test roots may never be the real host proc/cgroup roots" in rejected.stdout

        with (output / "series.json").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        run(["python3", str(VERIFIER), str(output)], env, success=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("AdGuard memory series tests: PASS")


if __name__ == "__main__":
    main()
