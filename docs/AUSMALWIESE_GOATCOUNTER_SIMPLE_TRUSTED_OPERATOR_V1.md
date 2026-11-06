# GoatCounter SIMPLE — one-shot trusted read-only operator source (#1364)

**SOURCE ONLY — not installed, not authorized to run on RPi5.**
This outcome adds an installer **source** and an importable bounded runner to the
existing GoatCounter SIMPLE offline/Cloudflare readback modules. It does not
create a new Tunnel, daemon, service, API client, key, credential, runtime grant,
database setting or public /count request. Existing rpi5-tunnel is reused.

## Frozen source and package

- Source repo: rozkalnsandris/RPi5_main, exact future approved main SHA.
- Installer source: scripts/install-ausmalwiese-goatcounter-simple-trusted-readonly-v1.py
- Runner source: scripts/ausmalwiese_goatcounter_simple_trusted_runner_v1.py
- Fixed install target: /usr/local/libexec/rpi5-goatcounter-simple-cloudflare-readonly
- Installer reads the exact clean main checkout at /home/andris/RPi5_main.
  It verifies exact HEAD, main branch, canonical origin and clean checkout.
  Every source byte must equal git show SHA:path from that exact tree.
- The installer packs exactly 9 source modules, including existing verified
  CloudflareClient, tunnel, route, readiness, evidence, Cloudflare readback and
  SQLite Collect readback. It writes an existing-Cloudflare-compatible
  release.json digest map (7 modules) and a separate trusted-release.json
  (all 9 modules), each with the same full SHA. No generic client.
- Release root is root:root 0700. Files are root:root 0400 except the runner
  0500. No symlinks, overwrite, upgrade, fallback installer, or cleanup.
  Manifest files are installed LAST. First mkdir consumes a future distinct
  owner-authorized installation mutation. Any later error is STOP with partial
  material left untouched; never retry/rollback/cleanup automatically.
- If an earlier installed release already occupies the fixed target, STOP.
  This issue does not authorize replacement or an alternate path.
- Calling the installer with no --apply only evaluates a source plan; the
  runner exposes only the source-check CLI. Source/CI must not invoke
  the actual installer or read protected files.

## Runtime requirements (NOT performed here)

The trusted runner checks the exact installed path, root identity, both
root-owned manifests and every pinned module byte before importing any
dependency. It has *no network/DB CLI and no token loader*. Protected functions
remain dormant unless a **separately authorized trusted caller** provides
exact source SHA, scope and independent owner authority. The installer DOES
NOT create owner-readonly-grant.json. A root-owned grant of the exact closed
schema is only one fail-closed input; its presence is not independently
sufficient evidence of who approved it or proof of one-shot consumption.
The external owner/controller must prove authority and consume its one-shot
permission before invoking a protected function; no in-source retry exists.

### Collect / active WAL

- Fixed DB path and private vhost; read only the numeric settings.collect
  with the already reviewed readback. Output is only
  COLLECT_DISABLED_1 / COLLECT_CANDIDATE_130 / STOP_COLLECT.
  Collect 130 is merely a proposal, NOT approved or confirmed LIVE.
- The runner *additionally* requires the actual DB, -wal and -shm paths
  to be visible under an OS-enforced read-only mount flag before it opens the
  SQLite mode=ro&cache=private transaction. It does not create such a mount.
  A future separately authorized caller must inspect that the mount/namespace
  cannot be bypassed by the caller's privilege, and that the shared-memory
  index is not modified. If the host does not satisfy this, STOP before read.
- No immutable=1 on active data. No database copy, checkpoint, sidecar
  removal, stop/restart or local data recovery. SQLite may update a mapped
  existing -shm wal-index even on logically read-only DB access, hence
  mode=ro alone is **not** a sufficient OS-level no-write proof.
- A future authorized sandbox can consider a narrowly scoped read-only bind
  view (e.g. systemd BindReadOnlyPaths with reduced mount capabilities) but
  that is NOT provisioned or allowed by this source PR; its exact behavior
  on RPi5 requires its own independent review.

### Cloudflare GET-only

- Future trusted caller supplies the *existing* CloudflareClient instance
  created in an independently authorized credential boundary. No token/key
  reader, account ID, zone ID, token or raw provider output is printed.
- Existing operator verified_release and GETOnly allowlist still apply:
  at most six GETs: exact zone; rpi5-tunnel list/configuration; Worker Routes;
  Worker Domains filtered separately for ausmalwiese.de and www.ausmalwiese.de.
  No PUT/PATCH/POST/DELETE, no retry, redirect or public /count hit.
- Cloudflare documents hostname and zone_id query filters for Worker Domains,
  but does **not** document page/per_page as request parameters. Its documented
  result_info.total_count is *unfiltered* total, not proof of the complete
  filtered host inventory. The existing sanitizer intentionally STOPs on any
  ambiguous pagination metadata; this can yield a legitimate false STOP,
  never treat source-only PASS as LIVE clearance or silently weaken it.

## Future exact owner gates (not granted by AUTO-RUN FULL #1364)

1. Review PR exact HEAD/CI/reviews and issue an explicit MERGE command.
2. Independently authorize exact RPi5 source sync + installation:
   host=rpi5, exact approved main SHA, existing target must be absent,
   exact installer/checkout/target, one mkdir+bounded file writes.
   No generic sudo/root permission beyond that one reviewed operation.
3. Independently authorize protected DB/settings READ and mount/identity
   safety, with only allowlisted sanitized results; or STOP before SQLite.
4. Separately authorize Cloudflare least-privilege token use and GET-only
   tunnel/zone/Worker route/domain reads, with owner-approved exact scope.
5. Verify client-IP forwarding and negative spoof proof; review German
   Datenschutzerklärung and approve the exact Collect mask before a **new**
   explicit settings/route/app activation decision. No analytics activation
   follows from a source merge.

No installed module provenance, real Collect value, real route inventory,
visitor IP trust, privacy approval or LIVE status is proven by these tests.
The previous installed release 6d92665bc098d7d58f05e65c7435414516804556
does not prove the source in this PR is installed.

## Disconnected verification

python3 tests/test-ausmalwiese-goatcounter-simple-trusted-readonly-v1.py

The existing source-level tests for the Cloudflare guarded GETs, pagination,
Worker intercepts and the SQLite WAL readback remain wired into make test.
All tests use synthetic material; nothing contacts RPi5, Cloudflare or a
protected DB.

Official docs (rechecked 2026-11-06):
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/walformat.html
- https://www.sqlite.org/uri.html
- https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/
