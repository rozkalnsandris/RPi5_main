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


## Provider-envelope failure mapping — Issue #1058

The first separately authorized protected collection on 2026-10-17 stopped
fail-closed with `STOP: trusted_runtime_failed`. Source review found the
installed normalizer expected a legacy synthetic versions list shape while the
current Cloudflare V4 reference documents `result.items`.

The corrected runtime keeps the same fixed three-GET plan and secret boundary.
It additionally catches the pre-detail versions parser boundary and returns the
static `versions_normalization_failed` STOP code without printing normalizer
exception text or provider payload. A future collection requires a new reviewed
release/install and a separate owner LIVE authorization; this source correction
does not authorize a retry.


## Bounded installed-runtime upgrade — Issue #1060

The currently installed protected inventory release is the reviewed #1056
release at `660deee749ca684e979a720fe69c66aee2b62e3d`. The original installer is
intentionally no-overwrite, so it remains the only valid path for a first
installation.

Issue #1060 adds a separate, exact-old-release upgrade mode. It accepts only
that one installed source SHA and only after proving all of the following before
any future mutation:

- current checkout is clean `main` at the exact expected new source SHA;
- current executor, normalizer and account-binding bytes equal that new HEAD;
- release directory remains root:root 0700 and is not a symlink;
- executor is root:root 0500, normalizer/release metadata are root:root 0400,
  and none of the three files is a symlink;
- installed executor and normalizer SHA-256 values equal the canonical bytes
  from Git commit `660deee749ca684e979a720fe69c66aee2b62e3d`;
- installed `release.json` SHA-256 equals the deterministic release metadata
  reconstructed from that same old Git commit and the already-reviewed account
  fingerprint.

The upgrade path then has exactly three fixed replacement targets: executor,
normalizer and `release.json`. It does not recreate or chmod the release
directory, touch the credential file, alter services/timers/sudoers/packages,
or call Cloudflare. GNU `install -T` is used only against the three fixed
paths after the no-symlink metadata gate; post-verification repeats exact
ownership/mode checks and SHA-256 checks for the new reviewed bytes.

A future dry preflight is selected only by the exact old release identity:

`--upgrade-from 660deee749ca684e979a720fe69c66aee2b62e3d`

A future mutation additionally requires the distinct confirmation string
`UPGRADE-AUSMALWIESE-STATS-WRANGLER-INVENTORY`. This documentation is source
contract only: #1060 grants no host replacement, credential access, Cloudflare
request or retry. Once the first replacement dispatch starts, any failure or
ambiguity is terminal STOP with no automatic retry, rollback or cleanup.


## Sanitized Versions diagnostic boundary — Issue #1069

The second authorized protected collection on 2026-10-17 stopped after only the
fixed Versions GET with `versions_normalization_failed`. No retry was made.
Issue #1069 keeps the request plan, credential boundary and accepted provider
contract unchanged, but lets the installed executor surface one bounded static
suffix such as `versions_normalization_failed_result_shape`. The executor
accepts only its own fixed diagnostic allowlist; an unknown classifier result or
classifier exception collapses to
`versions_normalization_failed_unclassified`.

The diagnostic path does not issue an extra request, retain provider payloads,
print raw version metadata, expose account/token data or authorize a future
collection. Any future installed-runtime replacement and any authenticated
Cloudflare read still require separate owner gates.
