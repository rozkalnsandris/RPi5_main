# GoatCounter SIMPLE Cloudflare GET-only preflight (#1358)

**SOURCE ONLY; no authenticated calls performed.** One small, existing-client
adapter replaces the undocumented Worker Domains `page/per_page` guess with
two documented exact `hostname` filters. No installer, service, token
provisioning, retry, root runner or configuration mutation is delivered.

`scripts/ausmalwiese_goatcounter_simple_cloudflare_readback_v1.py` calls
the injected `trusted_get` only for the active zone, the pinned remotely
managed `rpi5-tunnel` and its configuration, the zone's Worker Routes and
the exact `ausmalwiese.de` and `www.ausmalwiese.de` Worker Domains.
The source-only `...cloudflare_operator_v1.py` provides an allowlisted
GET-only adapter to existing `CloudflareClient`, **but run_guarded()
always STOPs before GET from an uninstalled Git checkout**. No CLI is exposed.

Every domain response must prove single-page completeness (page 1,
total_pages 1, count=total_count=returned rows, bounded per_page).
This is conservative: Cloudflare documents hostname filtering but does
not document page/per_page query controls; upstream result_info can report
global totals. Such inconsistent metadata means STOP, never a false PASS.
Any custom-domain result matching either public hostname (including
disabled/preview-only), overlapping Worker route or ambiguous Tunnel
ingress is rejected. Hostname filters cannot prove unrelated parent routes;
the apex is explicitly queried to cover www preview interception.

**Only fixed PASS_EDGE_SOURCE_ONLY/STOP_* and safe constants are returned.**
The operator must be installed with approved root-owned package metadata
and a trusted separate caller before the OS/source identity check permits
an injected GET. That trusted installation and its protected credential
reader are NOT delivered or authorized here; a fake fixture could always
produce a synthetic PASS. No source PASS is a LIVE proof.

Future explicit gates: exact RPi5 source sync/trusted installation; narrow
Cloudflare read-only authorization using Zone Read, Cloudflare Tunnel Read,
Workers Routes Read and Workers Scripts Read; separate authorized
GoatCounter Collect settings and IP spoof-negative proof; German privacy
review and separate activation approval. Existing /api/pageview PUT
operator must never be used for /count.

Official API:
https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/
https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/list/
https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/

Test:
`python3 tests/test-ausmalwiese-goatcounter-simple-cloudflare-readback-v1.py`
