# Ausmalwiese Worker settings GET — bounded source installer (#1002)

Status: **SOURCE ONLY / ACCOUNT BINDING PROPOSED IN #1004 / NOT INSTALLED**.

This outcome adds `scripts/install-ausmalwiese-worker-settings-get.py`, the
fixed account-binding contract, and offline regressions. No installed release,
privileged runtime change, Cloudflare token or GET is authorized by #1002.

## Read-only preflight / immutable scope

The unprivileged installer validates an exact reviewed `main` SHA, clean
checkout, canonical GitHub origin, the captured and Git-tracked executor and
sanitizer source bytes, and the dedicated account-binding source contract.
The account SHA-256 **must be independently verified and recorded in a
separately reviewed GitHub source change**. The account binding was initially `PENDING_INDEPENDENT_VERIFICATION` and
blocked all privileged writes. In source PR for #1004, the proposed binding
is pinned to the independently observed Worker account and exact evidence
URL. No host preflight or privileged install has been performed. Do not compute
the SHA from a token, Wrangler cache, protected configuration or guessed
account ID. Neither an offline synthetic fixture nor a prior D1 lookup
constitutes independent account verification.

The preflight requires sudo -n for *read-only* stat/test checks on fixed
root-owned, non-writable parent directories and verifies that **all targets**
are absent, including dangling symlinks. Fixed targets:

- `/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get`, root:root 0500
- `/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/`, root:root 0700
- `/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/sanitizer.py`, root:root 0400
- `/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/release.json`, root:root 0400

The release metadata pins the exact GitHub source SHA, both executable-source
digests and the independently verified fixed account SHA-256. No account ID,
token or protected runtime configuration is read during source work.

## Account binding source proposal — Issue #1004

The verified Worker was observed in authenticated Cloudflare Dashboard on
2026-10-13. The **only** retained account identifier is SHA-256
`3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34`. Reviewable evidence:
https://github.com/rozkalnsandris/RPi5_main/issues/1004#issuecomment-6153841286.
The installer pins both the exact digest and this immutable comment URL;
different account fingerprints, Workers, missing evidence and unrelated
comments fail closed. The raw Account ID, API token, OAuth cache and browser
profile are not part of the source. A changed `main` requires a fresh exact
checkout preflight.

## Future install operation — separately authorized

The installer offers a future one-shot `--apply --confirm` path. It is *not*
authorized by this source issue, code merge or README. After the exact
operator/source/capability and account-fingerprint gates have been explicitly
owner-approved, an independently authorized operator may consider the
bounded command. Do not execute it from this chat without the separate exact
LIVE approval.

The four fixed root mutations, only after preflight, are one mkdir of the
release directory, one install of the executable, one install of the pinned
sanitizer and one install of the release metadata. The unprivileged caller
dispatches only fixed sudo coreutils; **never repository Python as root**.
Installer copies already captured verified source bytes through stdin and
post-verifies root owner, strict modes, SHA-256. No automatic retry,
overwrite, rollback, cleanup or alternate executor is permitted after first
mutation. Multiple files are not an atomic transaction; failure can leave
partial installed state and requires STOP with a new owner decision.

The deployment is not authenticated until a dedicated, independently
authorized Workers Scripts Read credential is privately provisioned in the
reviewed root-owned secret path. No OAuth cache, environment dumping,
sudoers modification, Cloudflare API GET, DNS, settings or D1 mutation occurs
in this issue.

## Offline acceptance

`python3 tests/test-ausmalwiese-worker-settings-installer-v1.py` uses fake
git/sudo runners and synthetic account fingerprints. The `Makefile` CI suite
runs it. Offline tests are not LIVE evidence.

References: source PR #1001; `docs/AUSMALWIESE_WORKER_SETTINGS_EXECUTOR_V1.md`.
