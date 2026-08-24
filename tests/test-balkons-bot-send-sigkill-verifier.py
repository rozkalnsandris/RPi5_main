#!/usr/bin/env python3
from __future__ import annotations

import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/balkons-bot-send-sigkill-verifier"
DROPIN = ROOT / "ops/systemd/balkons-bot-no-sigkill.conf"
text = SCRIPT.read_text(encoding="utf-8")
dropin = DROPIN.read_text(encoding="utf-8")

assert text.startswith("#!/usr/bin/env bash\n")
assert SCRIPT.stat().st_mode & stat.S_IXUSR
assert "set -Eeuo pipefail" in text
assert "GIT_OPTIONAL_LOCKS=0" in text
assert "mode_must_be_explicit_and_unique" in text
assert "--check|--verify" in text
assert "--apply" not in text
assert "--rollback" not in text

for binding in (
    "--expected-repo-sha",
    "--expected-checkout-fingerprint",
    "--expected-verifier-sha256",
    "--expected-preflight-sha256",
    "--expected-dropin-sha256",
    "--expected-live-source-sha256",
):
    assert binding in text

assert "checkout_owner_must_be_nonroot" in text
assert "must_run_as_checkout_owner" in text
assert "verifier_hash_mismatch" in text
assert "preflight_hash_mismatch" in text
assert "dropin_source_hash_mismatch" in text
assert "dropin_target_already_exists" in text
assert "dropin_target_not_root_owned" in text
assert "dropin_target_mode_invalid" in text
assert "installed_dropin_hash_mismatch" in text
assert "dropin_dir_writable_by_nonroot" in text
assert "send_sigkill_not_disabled" in text
assert '[[ "$PF_SEND_SIGKILL" == "yes" ]]' in text
assert '[[ "$PF_SEND_SIGKILL" == "no" ]]' in text
assert "live_source_provenance_not_confirmed" in text
assert "preflight_reported_mutation" in text
assert "preflight_reported_write" in text
assert 'print("|".join(fields))' in text
assert "IFS='|' read -r" in text

# This tracked executable must remain purely read-only and non-root.
for forbidden in (
    "sudo ",
    "runuser ",
    "install ",
    "rm ",
    "mv ",
    "cp ",
    "tee ",
    "truncate ",
    "touch ",
    "mkdir ",
    "chmod ",
    "chown ",
    "systemctl daemon-reload",
    "systemctl restart",
    "systemctl reload",
    "systemctl stop",
    "systemctl start",
    "systemctl enable",
    "systemctl disable",
    "systemctl kill",
    "systemctl status",
    "systemctl cat",
    "docker ",
    "docker inspect",
    "mosquitto_pub",
    "mosquitto_sub",
    "/proc/",
    "git config",
    "safe.directory",
):
    assert forbidden not in text

assert 'printf \'RESULT=READY\\nMUTATION_STARTED=NO\\nWRITES_PERFORMED=NO\\n\'' in text
assert 'printf \'RESULT=PASS\\nMUTATION_STARTED=NO\\nWRITES_PERFORMED=NO\\n\'' in text

# No private host identity or LAN coordinates are allowed in source.
assert not re.search(r"/home/[A-Za-z0-9._-]+/", text)
assert not re.search(r"(?<![0-9])192\.168(?:\.[0-9]{1,3}){2}(?![0-9])", text)

# The reviewed drop-in consists of the exact two intended lines and nothing else.
assert dropin == "[Service]\nSendSIGKILL=no\n"
assert dropin.count("=") == 1

print("Balkons bot SendSIGKILL verifier source tests: PASS")
