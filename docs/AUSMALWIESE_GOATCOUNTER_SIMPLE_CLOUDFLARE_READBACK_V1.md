# GoatCounter SIMPLE: injected sanitized Cloudflare GET preflight (#1356)

**SOURCE ONLY.** This module contains no network client, token loader,
privileged runtime, CLI, filesystem I/O or LIVE mutation. The user must separately
approve any protected Cloudflare read, host sync or site-settings inspection.

The offline Python adapter accepts one injected trusted GET-only callable
using already reviewed CloudflareClient transport in a future authorized
runtime. It does not call the legacy /api/pageview writer and does not add
a second Cloudflare client. It reuses the account SHA256 binding from
ausmalwiese_goatcounter_tunnel_v1.py, the pure /count route prepare() from
ausmalwiese_goatcounter_simple_route_v1.py, and the Worker route classifier
from ausmalwiese_goatcounter_simple_evidence_v1.py.

Function collect_once(trusted_get=..., account_id=..., zone_id=...)
returns (STOP_*, None) or (PASS_EDGE_SOURCE_ONLY, reconstructed_edge).
The returned edge has exactly the four fields required by #1352/#1354:
remote_tunnel, routes (both public hosts), worker_routes, worker_custom_domains.
No account/zone/tunnel IDs, Worker names, route strings, provider messages,
raw configuration, credentials, headers or visitor addresses are returned.
All statuses are hardcoded. A fake injected callback can forge synthetic PASS:
this source check is NOT a cryptographic attestation or LIVE authorization.

## Exact GET-only allowlist

- /zones/{zone_id}: the supplied zone must be active, named ausmalwiese.de,
  and bound to the pinned account ID. A future runtime needs Zone Read.
- /accounts/{account_id}/cfd_tunnel?name=rpi5-tunnel&is_deleted=false&per_page=100:
  exactly one undeleted remotely managed tunnel with single-page proof.
- /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations:
  integer version and the existing pure prepare() must find both
  /count routes absent, but safe before each app fallback. Any existing
  or partial /count route, wildcard or inherited origin override STOPs.
- /zones/{zone_id}/workers/routes: Cloudflare documents one list with no
  pagination parameters. If optional result_info exists, demand one
  complete page. An intersecting or unrecognized pattern, even a no-script
  exclusion, returns STOP_WORKER. This covers /count*, wildcard overlaps,
  query-string interception, uppercase ambiguity and unsafe precedence.
- /accounts/{account_id}/workers/domains?page=N&per_page=20:
  up to five pages, with exact result_info count/page/per_page/
  total_count/total_pages consistency and unique row IDs. No hidden
  hostname filter; inspect all account domains and verify zone identity.
  Any target or parent-host Custom Domain, enabled or preview-enabled,
  is conservatively blocked (even if disabled; a stale/ambiguous state
  must not be mistaken for clearance). If the service does not honor
  pagination params/metadata, STOP_DOMAIN_PAGINATION.

Every GET path is constructed from pinned account/zone/tunnel identities;
one invocation per exact path, at most 12, never retries. The injected
trusted_get must be separately installed, authenticated, owner-approved,
GET-only, no redirects, no credentials in logs, no unapproved paths.
The source adapter cannot enforce an untrusted callback's implementation.
Never expose it publicly or use a synthetic status as a deployment gate.

## Independent future owner gates

1. Specific RPi5 checkout sync if needed (the earlier local checkout
   lacked /count source), separate approved GET-only Cloudflare operator,
   minimum Cloudflare Tunnel Read, Workers Routes Read, Workers Scripts Read
   and Zone Read. Protected config/tokens never enter chat or GitHub.
2. Separate authorized GoatCounter v2.7.0 runtime and sanitised
   SiteSettings.Collect readback (candidate 130 is not approved), and a
   negative spoof IP/HTTPS proxy trust proof.
3. German privacy notice reviewed with coloring-pages Draft PR #158,
   then explicit bounded owner authorization for any Cloudflare settings,
   app switch or public tracking change. Merge is NOT deploy approval.

Documentation:
https://developers.cloudflare.com/api/resources/zones/methods/get/
https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/
https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/list/
https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/
https://developers.cloudflare.com/workers/configuration/routing/routes/

Offline verification:
python3 tests/test-ausmalwiese-goatcounter-simple-cloudflare-readback-v1.py

No LIVE or Cloudflare request occurred as part of this source implementation.
