# GoatCounter SIMPLE — one trusted read-only preflight handoff (#1362)

**SOURCE ONLY. No runtime operation authorized or performed.**
The single next unit is a dormant, disconnected handoff of already merged
GoatCounter Collect WAL readback (#1360/#1361) and guarded Cloudflare GET
readback (#1358/#1359). This is **not** a trusted installed runner, a LIVE
preflight, a deploy script or a privacy approval. It does not introduce another
Tunnel, API client, service or credential.

## Exact source inventory and provenance

The source-only module
scripts/ausmalwiese_goatcounter_simple_preflight_handoff_v1.py
defines MODULE_SOURCE, an explicit 9-file source-to-future-release inventory.
plan_source_release() accepts only injected source bytes at exact source paths
and an exact 40-character main SHA; returns a stable SHA-256 inventory, with
deployable=false. No GitHub, filesystem, DB or Cloudflare access occurs.
The existing Cloudflare operator expects its own installed file to be named
operator.py. This inventory deliberately contains no installed root paths,
no writable installer, no source synchronization and no credential loader.

**Do not install this source plan as a runtime manifest.** The existing
Cloudflare operator uses a separately enforced root-owned release scope and
its own MODULES digest set. The new manifest is offline evidence ONLY; the
extra Collect and handoff modules would require an independently reviewed,
source-pinned installer, root-owned package verification and isolated runner
before any future operator invocation. A caller-supplied SHA/digest is not
trusted authentication. The previously installed release
6d92665bc098d7d58f05e65c7435414516804556 does NOT prove any of these
new files are installed. No RPi5 checkout change is authorized.

## Sanitized decision envelope

inspect_offline() checks only injected sanitized Collect and Cloudflare
evidence and a strict offline digest manifest; its response schema is exactly
schema_version, status, source_only=true, live_verified=false. The only
synthetic success code is PASS_OFFLINE_SHAPE_ONLY: never treat it as LIVE proof,
permission to read a DB, permission to issue Cloudflare API calls, approval
for Collect=130, or an authorization to activate analytics. Collect=1 gives
STOP_COLLECT_DISABLED; malformed/other Collect or Cloudflare inventory gives
fixed STOP codes. No raw database rows, token material, headers, visitor IPs,
account IDs, settings, paths or upstream provider errors leave the function.

The existing Collect module uses SQLite mode=ro&cache=private, PRAGMA
query_only=ON and validates the presence of pre-existing -wal/-shm.
**SQLite mode=ro is not an OS-level zero-write guarantee**: an open reader
may interact with the existing shared-memory WAL index. Do not run this helper
on a live protected database until a separate owner-authorized constrained
OS identity/permissions or read-only mount strategy has been reviewed.
Never use immutable=1 on a changing database and never delete/recreate
WAL sidecars, stop services or checkpoint under a read-only preflight.

The existing Cloudflare sanitizer uses the established CloudflareClient,
a pinned account and existing rpi5-tunnel; only six allowlisted GETs
(zone, Tunnel list+configuration, Worker Routes, exact apex and www Worker
Domains). Any ambiguous Worker route, inconsistent completeness metadata,
untrusted domain interception or provider failure means STOP. Cloudflare
documents exact hostname filtering; total_count may represent the entire
unfiltered account, so this conservative validator can STOP on a legitimate
provider result. It must never silently claim an absent route in that case.

## Separate future owner gates

1. Exact source SHA/current main, trusted owner identity, verified
   root-owned release and importer/checksum permissions, and one bounded
   RPi5 source synchronization/installation authorization (not here).
2. Protected GoatCounter settings READ authority with a constrained
   read-only OS identity and approved sidecar behavior. Expect only
   COLLECT_DISABLED_1, COLLECT_CANDIDATE_130 or STOP; never print data.
3. Explicit protected Cloudflare Tunnel/Worker GET authorization with
   existing least-privilege token, independent trusted opener and
   release-verified runner. No PUT/PATCH/POST/DELETE, no redirect/retry,
   no public /count hits, no raw Cloudflare output.
4. Independently prove real-client IP/forwarding behavior with a negative
   spoof test, and review the German Datenschutzerklärung plus the exact
   data collection mask. Finally require a distinct settings/route/app
   activation authorization; no merge grants LIVE rights.

At any uncertainty or failed first permitted operation: STOP, preserve only
allowlisted sanitized evidence, no retry/rollback/cleanup.

## Disconnected verification

python3 tests/test-ausmalwiese-goatcounter-simple-preflight-handoff-v1.py

This test uses injected synthetic sources, masks, Cloudflare statuses and
malicious canary strings. It never invokes the real RPi5 or Cloudflare.

## Official documentation (reviewed 2026-11-06)

- https://www.sqlite.org/wal.html
- https://www.sqlite.org/uri.html
- https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/
