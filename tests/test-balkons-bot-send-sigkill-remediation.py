#!/usr/bin/env python3
from __future__ import annotations

import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/balkons-bot-send-sigkill-remediation"
DROPIN = ROOT / "ops/systemd/balkons-bot-no-sigkill.conf"
text = SCRIPT.read_text(encoding="utf-8")
dropin = DROPIN.read_text(encoding="utf-8")

assert text.startswith("#!/usr/bin/env bash\n")
assert SCRIPT.stat().st_mode & stat.S_IXUSR
assert "set -Eeuo pipefail" in text
assert "MODE_COUNT" in text
assert "mode_must_be_explicit_and_unique" in text
assert "--check|--apply|--verify|--rollback" in text

for binding in (
    "--expected-repo-sha",
    "--expected-checkout-fingerprint",
    "--expected-artifact-sha256",
    "--expected-preflight-sha256",
    "--expected-dropin-sha256",
    "--expected-live-source-sha256",
):
    assert binding in text

assert 'DROPIN_TARGET="${DROPIN_DIR}/90-rpi5-no-sigkill.conf"' in text
assert 'PREFLIGHT_REL="ops/bin/balkons-bot-preflight"' in text
assert "send_sigkill_not_disabled" in text
assert '[[ "$PF_SEND_SIGKILL" == "yes" ]]' in text
assert '[[ "$PF_SEND_SIGKILL" == "no" ]]' in text
assert "live_source_provenance_not_confirmed" in text
assert "preflight_reported_mutation" in text
assert "preflight_reported_write" in text
assert "dropin_target_already_exists" in text
assert "installed_dropin_hash_mismatch" in text
assert "dropin_dir_writable_by_nonroot" in text
assert 'print("|".join(fields))' in text
assert "IFS='|' read -r" in text

# Root mutation mode must not make root the Git/preflight reader for a user-owned checkout.
assert "checkout_owner_must_be_nonroot" in text
assert 'runuser -u "$repo_user" -- env GIT_OPTIONAL_LOCKS=0' in text
assert "GIT_OPTIONAL_LOCKS=0" in text
assert "safe.directory" not in text
assert "git config" not in text

# The forward path is intentionally narrower than a service deployment.
apply_start = text.index("  apply)")
verify_start = text.index("  verify)")
apply = text[apply_start:verify_start]
assert apply.index("require_expected_drift") < apply.index("MUTATION_STARTED=\"YES\"")
assert apply.index("install -o root -g root -m 0644") < apply.index("systemctl daemon-reload")
assert apply.index("systemctl daemon-reload") < apply.index("require_preflight_pass")
assert "systemctl restart" not in apply
assert "systemctl reload" not in apply
assert "systemctl stop" not in apply
assert "systemctl start" not in apply
assert "systemctl enable" not in apply
assert "systemctl disable" not in apply
assert "systemctl kill" not in apply

# No automatic rollback after forward mutation. Rollback is an explicit mode.
assert "trap" not in text
assert "rollback_on_error" not in text
rollback_start = text.index("  rollback)")
rollback = text[rollback_start:]
assert rollback.index("rollback_requires_root") < rollback.index("MUTATION_STARTED=\"YES\"")
assert rollback.index('rm -- "$DROPIN_TARGET"') < rollback.index("systemctl daemon-reload")
assert "rm -rf" not in text

# The operator must not broaden scope into unrelated runtime surfaces.
for forbidden in (
    "sudo ",
    "docker ",
    "docker inspect",
    "mosquitto_pub",
    "mosquitto_sub",
    "systemctl restart",
    "systemctl reload ",
    "systemctl stop",
    "systemctl start",
    "systemctl enable",
    "systemctl disable",
    "systemctl kill",
    "systemctl status",
    "systemctl cat",
    "/proc/",
):
    assert forbidden not in text

# No private host identity or LAN coordinates are allowed in source.
assert not re.search(r"/home/[A-Za-z0-9._-]+/", text)
assert not re.search(r"(?<![0-9])192\.168(?:\.[0-9]{1,3}){2}(?![0-9])", text)

# Drop-in is deliberately tiny and cannot carry any other service setting.
assert dropin == (
    "# SOURCE ARTIFACT ONLY — installation is separately owner-gated under RPi5_main#192.\n"
    "[Service]\n"
    "SendSIGKILL=no\n"
)
assert dropin.count("=") == 1

print("Balkons bot SendSIGKILL remediation source tests: PASS")
