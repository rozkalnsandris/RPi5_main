# Ausmalwiese report secrets provisioner — installer source

**SOURCE ONLY. NOT INSTALLED. NO LIVE AUTHORITY.**

This source installs only the already reviewed report secrets helper from merged
PR #1072. It does not read or create the protected Wrangler secrets file and it
does not contact Cloudflare, Brevo, Turnstile or Wrangler.

## Fixed target

- source: `scripts/ausmalwiese_report_secrets_provisioner.py`
- pinned Git blob: `26a621b1608ae1c378bb274cb53a29fd48c2908c`
- future installed path:
  `/usr/local/sbin/rpi5-ausmalwiese-report-secrets-provision`
- required installed metadata: root:root, regular file, single link, mode `0500`

The installer itself must run unprivileged. Repository Python must never be run
as root.

## Read-only preflight

The default path requires:

- exact owner-supplied current `main` SHA;
- branch `main`, clean checkout and trusted GitHub origin;
- helper working-tree bytes equal Git `HEAD`;
- exact pinned helper Git blob and reviewed helper identity;
- root-owned, non-writable `/usr`, `/usr/local` and `/usr/local/sbin`;
- installed target absent, including dangling symlink;
- exact bounded sudo permission for the future copy command.

No protected secret path contents are read.

## Future one-shot install

The source reuses the already-reviewed fixed-helper installation primitive:

1. Copy only the verified helper bytes into a sealed anonymous `memfd`.
2. Recheck exact checkout, parent metadata, target absence and exact sudo command
   permission.
3. Dispatch exactly one root `cp` from `/dev/stdin` to the fixed target.
4. Verify only installed file metadata and SHA-256.

GNU coreutils `cp 9.1` uses `--no-clobber --verbose` and requires exact
C-locale verbose creation output plus exit status 0. GNU `cp >=9.6` uses
`--update=none-fail`. Versions 9.0 and 9.2–9.5 fail closed.

The fixed environment excludes `POSIXLY_CORRECT`. No shell, overwrite,
temporary disk staging, chmod/chown mutation, alternate target, retry, rollback
or cleanup is available. Any failure or ambiguity after the single root dispatch
is terminal STOP; the destination may need separate owner-reviewed recovery.

## Remaining gates

Merge of this source still does not install anything. A future sequence remains:

1. separately authorized read-only RPi5 preflight;
2. separately authorized one-shot helper installation;
3. separately authorized local foreground-TTY secret provisioning;
4. separately authorized one-shot Wrangler deploy and read-only verification.

Secret values must never be pasted into chat, GitHub, CLI arguments or logs.

## Offline tests

`python3 tests/test-ausmalwiese-report-secrets-provision-installer-v1.py`
uses a synthetic subprocess runner only. It covers source/blob drift, checkout
drift, unsupported coreutils versions, sudo capability denial, unsafe parents,
existing targets and dangling symlinks, sealed memfd metadata, exact one-copy
behavior, GNU 9.1 silent-skip/race handling, post-dispatch failures and the
no-retry/no-cleanup boundary.
