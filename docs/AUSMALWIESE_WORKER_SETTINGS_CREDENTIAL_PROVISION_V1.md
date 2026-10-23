# Ausmalwiese Worker settings read credential — private owner-TTY source (#1009)

**SOURCE-ONLY PROPOSAL.** No credential, Cloudflare token, API call, root helper installation, or LIVE permission is included in this issue or PR.

## Verified, distinct states (2026-10-13)

- GitHub `main` baseline at task activation: `6c55e46d43889fed2a17770d0f466c79b1db736a`.
- Cloudflare account SHA-256: `3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34`. The raw account ID is **not** source material. Evidence: https://github.com/rozkalnsandris/RPi5_main/issues/1004#issuecomment-6153841286
- On RPi5, under a **separate consumed LIVE authorization**, the existing fixed GET executor, sanitizer and release metadata were installed. Owner `root:root`, modes `0500`, `0400`, `0400`, release directory `0700` were confirmed by a later read-only `sudo stat` check on 2026-10-13. This is evidence of installation only, **not** of credential availability or GET success.
- The **new** `scripts/ausmalwiese_worker_settings_provisioner.py` in issue #1009 is **not installed**. Its repository copy must **never** be run as root. Even after source merge, token creation, helper installation, credential provisioning and Cloudflare GET remain separate authorization steps.

## New source-only installer planning — Issue #1011

The reviewed source-only helper installer is proposed in
`scripts/install-ausmalwiese-worker-settings-provisioner-v1.py`.
Its bounded GNU `cp` exclusive-create mechanism, exact preflight
requirements and remaining host capability checks are documented in
`docs/AUSMALWIESE_WORKER_SETTINGS_PROVISION_INSTALLER_V1.md`.
It is **not installed or authorized for LIVE execution**. Merging
this source changes neither helper installation nor token/GET permissions.

## GNU coreutils 9.1 compatibility — Issue #1016 (SOURCE ONLY)

RPi5 read-only observation on 2026-10-14 confirmed GNU `cp 9.1`,
whereas the originally merged #1011 installer required `>=9.4`.
The #1016 source correction uses the version-specific, source-reviewed
GNU 9.1 `--no-clobber --verbose` branch plus an exact stdout-and-exit
check to disambiguate silent "destination already exists" success.
See `docs/AUSMALWIESE_WORKER_SETTINGS_PROVISION_INSTALLER_V1.md`.

**This is neither permission nor proof of runtime installation readiness.**
The actual GNU 9.1 binary, exact restricted `sudo` command capability,
trusted parents and absent target require a separately authorized
read-only host preflight before any possible LIVE installation. Source merge,
checkout synchronization, helper installation, Cloudflare token creation,
owner-local TTY credential provisioning and GET remain separate steps.

## Future private credential contract (not authorized now)

1. A future *separately authorized* action in the authenticated Cloudflare Dashboard must explicitly create or select a dedicated **account-scoped Workers Scripts Read** API token for the verified account, with no Write, D1, other account, or zone permissions. The owner must never paste the token into ChatGPT, GitHub, a command argument, browser logs or RDC output.
2. A **separately reviewed and authorized immutable helper installer** must pin this helper's exact merged source bytes and install them to `/usr/local/sbin/rpi5-ausmalwiese-worker-settings-provision`, owner `root:root`, mode `0500`, no symlink/hardlink. Only this fixed installed file can run. Do not run repository Python as root. No `sudoers` or shell-history changes are implied.
3. On the owner-controlled **local foreground controlling TTY**, under a separately issued exact LIVE provisioning permission, the fixed root-owned helper accepts only public static `--expected-release-main` and `--confirm` arguments. It opens `/dev/tty` and reads both the exact lowercase account ID and the dedicated API token with terminal echo disabled. No secret is accepted from arguments, stdin, env vars, clipboard automation, Wrangler cache or an agent-controlled tool. The owner must not run it from a logging remote session.
4. Before prompting, the helper validates its fixed installed identity and immutable installed GET-release metadata and hashes; source identity is the *installed* GET release SHA `6c55e46d43889fed2a17770d0f466c79b1db736a`, **not** any later GitHub `main`. A later GET-release update requires independently reviewed re-pinning.
5. It checks root-owned non-writable ancestors, an existing private Cloudflare directory with mode `0700`, and the *absence* of the one destination (including symlinks). It validates the account fingerprint in memory **before requesting the token**, checks strict token format, and revalidates the parent inode and destination absence.
6. A separately authorized one-shot provisioning writes only `/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json` via an exclusive `O_CREAT | O_EXCL | O_NOFOLLOW` open relative to the pinned directory fd, owner `root:root`, mode `0600`. JSON has exactly `worker`, `account_id`, and `api_token`. The content is not printed or staged on disk. After first destination-open dispatch, any failure or ambiguity is **STOP without retry, rollback, cleanup, replacement or alternate transport**. It verifies only protected file metadata.
7. A later independently approved, single read-only Worker settings GET is yet another gate. Neither the source PR nor private credential provisioning authorizes this GET.

The helper does not call the Cloudflare API or create token permissions; it only prepares a fixed local storage operation for a future, separately authorized owner-side procedure. The concrete installation, provisioning and GET commands must be reviewed against fresh host/source baselines and require explicit owner permission. Do **not** treat static `--confirm` text as owner authorization.

## Offline acceptance

`python3 tests/test-ausmalwiese-worker-settings-provisioner-v1.py` uses synthetic strings and mocked IO only. It does **not** access `/dev/tty`, `/etc/rpi5-secrets`, Cloudflare, or LIVE. `make test` includes this test file.

Fail-closed cases cover uninstalled/untrusted helper; wrong, stale or malformed installed release; wrong Worker/account digest; invalid token; unavailable, background or invalid controlling TTY; unsafe parent/mode/symlink; pre-existing credential; destination drift; partial write with no retry; unapproved confirmation and secret-free error messages.

**Security distinction:** Python string lifetime cannot provide guaranteed memory zeroization. This design prevents deliberate secret output and staging but does not claim hardened-memory confidentiality. Any post-install operational plan must account for this limitation.
