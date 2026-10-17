# Ausmalwiese Stats Wrangler protected inventory runtime + installer (#1056)

SOURCE ONLY / NO MERGE / NO LIVE / NO HOST INSTALL / NO CLOUDFLARE REQUEST /
NO CREDENTIAL ACCESS.

## Purpose

This outcome prepares a fixed protected runtime for the normalized Stats Wrangler
inventory collector merged in #1054. It does not install or run that runtime.

A future separately authorized invocation will perform exactly three read-only
Cloudflare Workers GETs for coloring-pages-stats-v1:

1. versions page 1, per_page 2;
2. deployments page 1, per_page 2;
3. exact latest-version detail.

The installed normalizer is the exact hash-pinned merged
scripts/ausmalwiese_stats_wrangler_inventory_v1.py source. Raw provider JSON is
passed only in memory to that normalizer. Successful stdout contains only:

- inventory;
- inventory_sha256.

## Trust and credential boundary

The runtime is a new, dedicated release and does not modify or widen the
existing script-settings GET release.

Proposed installed paths:

- /usr/local/sbin/rpi5-ausmalwiese-stats-wrangler-inventory
- /usr/local/libexec/rpi5-ausmalwiese-stats-wrangler-inventory/normalizer.py
- /usr/local/libexec/rpi5-ausmalwiese-stats-wrangler-inventory/release.json

The existing dedicated read credential format/path is reused only as a future
input boundary:

/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json

Its exact keys remain worker, account_id and api_token. This source neither
creates nor replaces that file. A future runtime validates the fixed Worker,
lowercase account-ID syntax, the reviewed SHA-256 account fingerprint and token
shape before any network request. It never prints the account ID or token.

Account fingerprint:

3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34

## Fixed network behavior

The executor source uses Python http.client directly with certificate/hostname
validation and the fixed host api.cloudflare.com. It does not use environment
proxy discovery, Wrangler OAuth cache, a global API key, arbitrary URLs or
caller-provided paths.

Every future invocation is bounded to:

- method GET;
- exactly three requests;
- 10 second timeout;
- 64 KiB maximum response body per request;
- Accept-Encoding identity;
- zero redirects;
- zero retries.

Any HTTP error, redirect, malformed response, oversized response, request-plan
drift or provider ambiguity is a static STOP. Upstream response bodies and
exception details are not printed.

## Installed identity

The runtime is eligible only when executed as root from the exact installed
entrypoint. The release metadata and all installed files must be root-owned,
non-symlink regular files with the reviewed modes:

- release directory 0700;
- executor 0500;
- normalizer 0400;
- release.json 0400.

release.json binds:

- exact RPi5_main merged main SHA supplied to the installer/runtime;
- repository and Worker;
- executor SHA-256;
- normalizer SHA-256;
- reviewed account SHA-256.

Repository-checkout execution as root is deliberately rejected.

## Installer source

scripts/install-ausmalwiese-stats-wrangler-inventory-v1.py is a future
no-overwrite installer. Its preflight runs unprivileged and requires:

- exact main branch and exact expected 40-hex HEAD;
- clean checkout;
- trusted GitHub origin;
- tracked executor, normalizer and account-binding bytes equal HEAD;
- root-owned non-writable /usr/local parent chain;
- every dedicated target absent, including symlinks.

It installs only four objects/actions:

1. create the dedicated 0700 release directory;
2. install the executor 0500;
3. install the normalizer 0400;
4. install release.json 0400.

It does not install or run repository Python as root, alter sudoers, create a
service/timer, touch the credential file, change the existing settings GET
release, or call Cloudflare.

After the first install mutation is dispatched, any failure or ambiguity is
terminal STOP. There is no retry, rollback, cleanup, unlink, reset or alternate
installer path.

## Authorization boundaries

This merged source, when later approved, still does not itself grant:

- host installation;
- credential existence/read/verification;
- authenticated Cloudflare GETs;
- token creation or permission changes;
- the one-time non-strict Wrangler takeover.

Those remain separate explicit owner gates. Merge never authorizes LIVE.
