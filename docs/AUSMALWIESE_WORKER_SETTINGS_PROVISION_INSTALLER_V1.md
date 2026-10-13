# Ausmalwiese fixed private TTY helper — exclusive installer source (#1011)

**SOURCE-ONLY. NOT INSTALLED. NO LIVE AUTHORIZATION.** This document describes a *future* separately owner-authorized bounded root installation; it does not authorize it or token handling.

## Current source and runtime distinctions (2026-10-13)

- `scripts/ausmalwiese_worker_settings_provisioner.py` was reviewed in #1009/PR #1010. It is a private owner-controlling-TTY credential *source*; its installed path `/usr/local/sbin/rpi5-ausmalwiese-worker-settings-provision` was absent at the last read-only RPi5 check. The new installer source here has not been run against RPi5.
- The **different** GET executor `/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get` and its sanitizer/release metadata were previously installed and independently verified on RPi5 under separate consumed LIVE approvals; source SHA `6c55e46d43889fed2a17770d0f466c79b1db736a`. Do **not** reinstall this GET release.
- Current `RPi5_main/main` at #1011 activation was `6746dace26a9a0130f5ded8558bed5ae47ce6a32` (original issue baseline `3750ccfa376011e979783419549b1e89e0796148`, superseded by one unrelated redirect commit). Any future preflight requires the then-current exact **merged** main SHA and a clean trusted checkout; never reuse these SHA values as an authorization.
- Verified Worker `coloring-pages-stats-v1`; pinned Cloudflare account **SHA-256 only**: `3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34`; evidence: https://github.com/rozkalnsandris/RPi5_main/issues/1004#issuecomment-6153841286. No raw account ID, API token or token digest in GitHub.

## Fixed source-only installer

`scripts/install-ausmalwiese-worker-settings-provisioner-v1.py` runs **unprivileged** and has a read-only default preflight. It demands exact main SHA, verified `main` branch, clean checkout, trusted GitHub origin, and exact Git-tracked bytes of the fixed credential-helper source. It parses that source with `ast` **without executing it**, and checks the entrypoint path, Worker, account fingerprint, installed GET release identity, local protected credential destination and fixed confirmation marker.

The read-only preflight checks `sudo -n` access to a bounded `/usr/bin/cp` capability and exact copy arguments, along with root-owned, non-writable parent directories, and absence of the target including dangling symlinks. It requires **GNU coreutils cp >= 9.4** and the specific `--update=none-fail` semantic. This is a **future-host capability prerequisite**; the source-only #1011 work has not verified the actual host's coreutils version or privilege rule. If the pinned prerequisites are absent, preflight must STOP without host mutation. It does not read `/etc/rpi5-secrets` or other protected config.

### Why not `install -m 0500`?

The ordinary `install` executable can replace a target created between a prior absence check and the write. That violates the issue's no-overwrite rule. See GNU [install invocation](https://www.gnu.org/software/coreutils/manual/html_node/install-invocation.html) and [cp invocation](https://www.gnu.org/software/coreutils/manual/html_node/cp-invocation.html).

For the **future separately authorized one-shot** `--apply` operation:

1. Complete preflight and capture the **Git-tracked** source bytes in unprivileged memory. Create an *anonymous* Linux `memfd` (no disk staging); write only those source bytes, set its mode `0500` and seal it against modification/growth/shrink.
2. Recheck exact checkout and target absence, then dispatch **one** root command: `sudo -n /usr/bin/cp --update=none-fail --preserve=mode -T -- /dev/stdin /usr/local/sbin/rpi5-ausmalwiese-worker-settings-provision` with the sealed memfd inherited as stdin. The invocation environment is fixed and **excludes `POSIXLY_CORRECT`** (which otherwise allows a dangerous dangling-symlink fallback).
3. GNU cp's new-destination path uses `openat(..., O_CREAT | O_EXCL, ...)` (reviewed [coreutils source](https://github.com/coreutils/coreutils/blob/master/src/copy.c)); `--update=none-fail` refuses an existing destination. `--preserve=mode` uses the sealed memfd's executable permission bits. Root executes only the fixed coreutils command: **no repository Python and no arbitrary root command**, no temp file, no alternate target or cleanup. The single fixed coreutils operation includes its own file and metadata creation; there is no separate `chmod` root command.
4. After dispatch, verify only the installed **helper source** file's exact `root:root 0500`, regular-file/single-link metadata and SHA-256. No GET release or protected credentials are touched. Any return error, timeout, uncertain dispatch or failed post-verification is **STOP**, with no retry/rollback/cleanup. The file may be partially created on error, so it must never be overwritten.

The future exact host preflight must independently confirm its deployed coreutils version, sudoers' **exact** command capability and the installed GET release identity, with a separately authorized LIVE operator gate. The source tests are fake-runner only and do not prove actual host readiness or permission to install.

## Four separate owner decisions

- **Install this new helper**: fresh exact merge SHA, RPi5, executable path, one exclusive-create operation; distinct LIVE authorization.
- **Generate least-privilege Cloudflare API token**: authenticated owner account, dedicated account-scoped `Workers Scripts Read` only; **separate Cloudflare authorization**.
- **Provision the credential locally**: dedicated owner-controlled foreground non-echoing TTY, helper installed and independently verified, `root:root 0600` protected destination; **separate LIVE authorization**. Never paste token or raw account ID into chat/agent-controlled tools.
- **Run a single read-only GET** of the fixed Worker's script settings: yet another bounded owner gate. Neither this source PR nor helper installation permits a GET.

## Offline acceptance

`python3 tests/test-ausmalwiese-worker-settings-provision-installer-v1.py` is wired into `make test`. Mocked Git/sudo/filesystem regression cases include dirty and stale checkout, untrusted origin, mismatched fixed source constants, absent or unsafe root parent, existing file or dangling symlink, unsupported coreutils version/privilege, sealed memfd, exact one root invocation, negative post-verification and fail-closed no retry. No root mutation or real credential input is used.

**Residual risk:** the operator must treat errors after dispatch as partial/unknown installed state. No permission, retry or recovery is implied by this documentation.
