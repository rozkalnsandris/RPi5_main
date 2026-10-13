# Ausmalwiese — fixed Cloudflare Worker script-settings GET (source-only)

Status: SOURCE ONLY. No installed trusted executor, no Cloudflare GET, no tokens and no LIVE action.

## Exact scope and provider reference

The only target is Worker coloring-pages-stats-v1 on a separately pinned and
verified account. The only operation is one GET at:

https://api.cloudflare.com/client/v4/accounts/{trusted_pinned_account_id}/workers/scripts/coloring-pages-stats-v1/script-settings

Official API: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/

The Cloudflare API documents Workers Scripts Read or Workers Tail Read as
acceptable read capabilities (it also accepts Scripts Write, which is not
desired for least privilege). This source does not create or request a token.

## Delivered offline adapter

scripts/ausmalwiese_worker_settings_get.py exports fixed_url,
sanitize_settings, and collect_once. The trusted caller injects a GET-only
transport and a pinned 32-character lowercase hexadecimal account ID.
It produces one sanitized result containing only known boolean settings,
finite sampling rates in [0,1] and destination COUNTS. Absent values remain
null / unknown, not false. Secret bindings, tags, consumer names, URLs,
raw API payloads, exception details, credentials and account IDs are omitted.
Any API failure or unexpected field type yields one stable fail-closed code.
Never retry automatically and never print the upstream response.

## Transport-integration design

The no-credential transport contract and threat model are reviewed separately
in `docs/AUSMALWIESE_WORKER_SETTINGS_TRANSPORT_V1.md`; the runtime executor
is **not** implemented or authorized in this source PR.

## Trusted executor source

The source-only fixed GET runtime is implemented in
`scripts/ausmalwiese_worker_settings_executor.py`, with a separate install
preflight contract in `docs/AUSMALWIESE_WORKER_SETTINGS_EXECUTOR_V1.md`.
It has **not** been installed or used for any authenticated Cloudflare GET.

## Critical trust boundary

This source does NOT implement an authenticated HTTP transport, install
a privileged helper, inspect host OAuth storage, call Wrangler internal
modules, or access any protected runtime configuration. In particular,
an authenticated transport must NOT be improvised by reading Wrangler's
OAuth files, process environment, browser storage or secret material from
an untrusted shell, and must not forward tokens through chat or RDC.

A future exact-authorized, reviewed, installed trusted executor must:

1. Bind the actual Cloudflare account ID internally to an independently
   verified fixed account and the fixed Worker; do not accept account ID,
   endpoint, method, headers or token from user arguments.
2. Provide a GET-only authenticated in-process transport for precisely the
   URL above, with no redirects, no retries, bounded response size and
   timeout, and with no fallback to other credentials or Cloudflare APIs.
3. Keep OAuth refresh and secrets entirely inside that approved trust
   boundary, with separate owner authorization for credential access.
4. Return only the allowlisted sanitized result or stable failure class.
   Never emit raw response bodies, exception text, account metadata or
   authorization headers. Do not collect or print visitor logs.
5. Run only after separate source review, release binding, exact host
   preflight and explicit single-use owner authority. A merged PR is not
   an install or a Cloudflare read authorization.

Until that integration exists, script execution deliberately exits with
SOURCE_ONLY and no network connection. Any displayed Observability state
from offline fixtures is synthetic and is NOT evidence of LIVE settings.

## Offline checks

Run python3 tests/test-ausmalwiese-worker-settings-get-v1.py.
Makefile test includes this suite for GitHub CI. Tests use fake responses
and never contact Cloudflare or read credentials.

Exclusions: Cloudflare writes, settings changes, token refresh, D1 queries,
Worker deployments, host install, sudo, live logs, secrets, and MERGE.
