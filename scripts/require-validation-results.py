#!/usr/bin/env python3
from __future__ import annotations

import os

RESULT_NAMES = (
    "REGRESSIONS_RESULT",
    "API_CONTRACT_RESULT",
    "TARGETED_LEGACY_RESULT",
    "SECRET_SCAN_RESULT",
    "PUBLIC_SAFETY_RESULT",
    "GITLEAKS_RESULT",
    "PUBLIC_AUTOMATION_RESULT",
    "WORKFLOW_SECURITY_RESULT",
)


def main() -> int:
    failed = False
    for name in RESULT_NAMES:
        result = os.environ.get(name)
        if result is None:
            print(f"{name}=missing")
            failed = True
            continue
        print(f"{name}={result}")
        if result != "success":
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
