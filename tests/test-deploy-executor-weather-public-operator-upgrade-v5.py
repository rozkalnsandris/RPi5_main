from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_SHA = "14501ddbe2853d8072464291b338c29a029dd3cf"
HISTORICAL_TEST = "tests/test-deploy-executor-weather-public-operator-upgrade-v5.py"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "weather-v5-reviewed"
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(ROOT),
                "worktree",
                "add",
                "--detach",
                str(checkout),
                HISTORICAL_SHA,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            subprocess.run(
                [sys.executable, str(checkout / HISTORICAL_TEST)],
                cwd=checkout,
                env=env,
                check=True,
            )
        finally:
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(ROOT),
                    "worktree",
                    "remove",
                    "--force",
                    str(checkout),
                ],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
