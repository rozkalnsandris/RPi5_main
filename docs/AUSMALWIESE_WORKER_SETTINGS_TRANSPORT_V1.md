# Ausmalwiese — trusted Worker-settings GET transport design (source only)

Status: **TRUSTED EXECUTOR SOURCE IMPLEMENTED / NOT INSTALLED / NO LIVE GET**.
Companion: \`docs/AUSMALWIESE_WORKER_SETTINGS_GET_V1.md\` and
\`ops/contracts/ausmalwiese-worker-settings-get-v1.json\`.

## Verified upstream API

Cloudflare documents an authenticated GET for Worker \`coloring-pages-stats-v1\`:

\`GET https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/coloring-pages-stats-v1/script-settings\`

Official documentation:
https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/

It accepts \`Workers Scripts Read\`, \`Workers Tail Read\`, or \`Workers Scripts Write\`.
**Only Workers Scripts Read is the intended least-privilege option** for
a future dedicated credential. The permission capability does **not**
establish which rights the currently logged-in Wrangler OAuth session has.

## Source integration — not installed

The future trusted GET executor now exists in source at
`scripts/ausmalwiese_worker_settings_executor.py` with pinned release
metadata checks, dedicated credential guard and one bounded HTTPS GET.
The operator remains **not installed, not credentialed, and not executed**;
see `docs/AUSMALWIESE_WORKER_SETTINGS_EXECUTOR_V1.md`.

The existing source-only sanitizer
\`scripts/ausmalwiese_worker_settings_get.py\` accepts exactly one injected
trusted GET callback. It has no OAuth, network or secret access. The future
trusted runtime (separately reviewed and installed) must bind:

1. An internally verified Cloudflare account ID and **fixed Worker**, with
   exact request method/path, without accepting caller-controlled URL, method,
   account ID, authorization header, script name or query parameters.
2. One authenticated in-process GET. Enforce TLS validation, JSON content
   type, 10-second timeout, **32 KiB maximum raw response**, zero redirects,
   zero automatic retries, and no fallback credentials. All of these must
   be enforced by the trusted runtime, not assumed from the sanitizer alone.
3. A hardened secret/authentication boundary, with no credential or OAuth
   artifacts in chat, RDC, command arguments, environment dumps, stdout,
   logs, GitHub, child processes or code repositories. Bind a root-owned
   trusted operator to a specific reviewed installed release. Do not read
   Wrangler's profile/OAuth cache from a general-purpose Python shell.
4. Sanitization **before** output: only booleans, finite sampling rates and
   destination counts from the existing sanitizer. Do not emit account ID,
   destinations, tail consumers, raw Cloudflare errors, upstream response
   bodies, authorization headers or tokens. Missing values stay unknown,
   not \`false\`.
5. A strict fail-closed post-error disposition. If the trusted operation has
   been dispatched and fails or returns an ambiguous result, no retry,
   alternate API route, cleanup or credential rotation is implicit.

The \`ops/contracts/ausmalwiese-worker-settings-transport-design-v1.json\`
is the reviewable machine contract. It describes limits and gates; the
executor HTTP client and protected credential reader now exist **in source
only**. No root installer, installed trusted transport or credential has
been created or authorized.

## Authentication decision still open

On the RPi5 host, \`wrangler deployments status\` and \`wrangler d1 info\`
were observed working under an existing login. The stable Wrangler 4.135.0
CLI, however, did not expose a reviewed \`script-settings\` GET operation.
It is **not authorized or safe** to extract Wrangler's cached OAuth
credentials or call an unreviewed internal Wrangler API to fill this gap.

A future owner and security review must select, validate and explicitly
authorize one suitable **trusted** authentication lane:

- A dedicated, minimally scoped \`Workers Scripts Read\` service credential
  provisioned privately to a separately installed fixed GET operator; or
- A provider-supported trusted OAuth/SDK surface verified to keep all token
  handling inside an approved protected executor. No such surface is
  established by this design.

The dedicated read-only token lane is now the selected **source design**, but no
credential has been created, provisioned, read or used. No additional Cloudflare
permissions, LIVE setup, credential reads or host changes are implied.

## Offline acceptance and future LIVE gate

Offline tests in \`tests/test-ausmalwiese-worker-settings-transport-design-v1.py\`
cross-check the fixed endpoint and sanitizer, runtime limits,
non-authentication, non-deployment and fail-closed output expectations.
\`make test\` runs them with synthetic payloads only.

Before a real GET: freeze and review exact source/head; independently
verify actual account/Worker binding and required permission; review an
actual installed trusted implementation with proper bounded GET semantics;
perform the separately owner-approved host preflight; then obtain one
exact authorization for the credential-protected GET. A passing source CI
or GitHub merge proves none of those runtime facts.

**Out of scope:** installing or executing the runtime transport,
Cloudflare/D1/Worker mutations, OAuth/token access or refresh, RPi5
runtime writes, secrets, permissions, settings, merge and any LIVE action.
