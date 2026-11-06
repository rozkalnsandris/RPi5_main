# GoatCounter SIMPLE — one-shot trusted read-only operator source (#1364)

**Source-development contract; protected runtime operations are not authorized.**
The existing fixed release `7767caf9b5a5921aac43702af75ba2abe0e77d7d`
was independently installed on RPi5 and passed one root-owned
`python3 -I -B` source check (2026-11-06). This confirms **source integrity
only**, not Cloudflare/Collect settings or LIVE analytics. Subsequent #1368
source edits are NOT installed, and cannot be silently applied to that immutable
release. This outcome adds an installer **source** and an importable bounded
runner to the existing GoatCounter SIMPLE offline/Cloudflare readback modules. It does not
create a new Tunnel, daemon, service, API client, key, credential, runtime grant,
database setting or public /count request. Existing rpi5-tunnel is reused.

## Frozen source and package

- Source repo: rozkalnsandris/RPi5_main, exact future approved main SHA.
- Installer source: scripts/install-ausmalwiese-goatcounter-simple-trusted-readonly-v1.py
- Runner source: scripts/ausmalwiese_goatcounter_simple_trusted_runner_v1.py
- Fixed install target: /usr/local/libexec/rpi5-goatcounter-simple-cloudflare-readonly
- Installer derives the checkout root from its own checked-out scripts/ path.
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

## Root Git trust preflight — #1366 source correction

The first separately authorized install attempt (2026-11-06) synchronized
the RPi5 checkout to the reviewed main SHA and passed the unprivileged source
plan, but the **one** root installer invocation returned
`STOP_INSTALL_UNCERTAIN` before the install target was created.
The consumed LIVE authorization is **not** reusable; no retry, rollback,
cleanup or alternate host path was attempted. Git's documented `safe.directory`
ownership gate is a likely, but not retrospectively proven, cause: the
installer previously removed `SUDO_UID` from its subprocess environment.

The corrected installer checks the real UID, mode and directory type of the
checkout, `.git` and the installer source before any Git subprocess. Under
sudo-root, it requires an exact decimal, non-root `SUDO_UID` that matches the
ownership of **all three**, rejects symlinked or group/other-writable
metadata, then forwards only that validated `SUDO_UID` to Git.
Unprivileged source-plan checks require the same unprivileged owner.
All inherited Git/environment config is dropped; core.fsmonitor is disabled,
hooks are disabled, Git locks are optional-disabled, stderr is discarded.
No `safe.directory=*`, global Git config or filesystem permissions change.
Git identity or ownership failures yield the sole sanitized code
`STOP_GIT_TRUST`; other failures remain `STOP_INSTALL_UNCERTAIN`.

This is **only a source fix** with disconnected adversarial tests. A later
RPi5 installation needs a **new exact owner authorization**, with current main,
host and target freshness checked again; nothing here grants a second attempt.

Official Git documentation: https://git-scm.com/docs/git-config/2.54.0
(see `safe.directory` and the root/`SUDO_UID` exception).

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

## One-shot diagnostic handoff — #1368 (SOURCE ONLY)

Use the **existing** `rpi5-tunnel`, the nine already reviewed source modules,
and the **existing** `CloudflareClient`. No new tunnel, service, token reader,
provider client or public `/count` traffic is necessary. The only public-safe
result is a fixed `PASS_EDGE_SOURCE_ONLY` or `STOP_CLOUDFLARE`.

The trusted runner exposes a `--source-check` CLI only. A *separately
authorized, independently trusted caller* must use
`cloudflare_once(expected_source_sha, owner_gate, client_factory, account_id,
zone_id)` **in process**. Its `owner_gate(scope, SHA)` must independently
authenticate and consume an exact owner approval **before** returning the
literal `True`; a callback or the root-owned `owner-readonly-grant.json`
ALONE is **not** an authorization receipt. A caller also must have permission
to read the existing credential capability through an independently approved
boundary; the injected `client_factory(verified_CloudflareClient_class)`
must return exactly that already reviewed class. The runner itself never
loads tokens or outputs account IDs, tokens, provider responses or private
paths. All six possible calls are guarded one-shot **GET**, with no retry.
Any missing/invalid grant, owner gate, client or API proof returns a fixed STOP.
Because Worker Domain response pagination metadata can be ambiguous, a
conservative `STOP_CLOUDFLARE` is not evidence of an actual conflict.

Import safety: protected module loading requires Python **`-I -B`**,
a preloaded, verified **standard-library** `operator` module, and
no foreign preloaded release dependencies. The fixed release path is added
only temporarily and removed in a `finally` block. This avoids local
`operator.py` shadowing Python's standard library without renaming or
overwriting installed release files. See
https://docs.python.org/3.11/using/cmdline.html.

`Collect` is **OFF by default**: `collect_once` requires a distinct
authorized `COLLECT` grant, a trusted `owner_gate`, AND an independent
`readonly_proof` that an enforced mount namespace prevents even root
remount/writes to the SQLite database, existing active WAL and `-shm`.
The runner also independently checks `ST_RDONLY` for all three.
No such proof or inability to prevent physical `-shm` writes results in
`STOP_COLLECT` **before opening SQLite**. No `immutable=1`, copies,
checkpoints, sidecar cleanup or new database service.

**Future single owner decision (NOT granted):** after final exact-head merge
and fresh RPi5 preflight, independently authorize a **bounded replacement
plan for the existing immutable root-owned release** (never overwrite it
by default), an exact source SHA and digest verification, a separately issued
one-shot root-owned grant with authenticated owner provenance, and—only if
explicitly approved—the existing-credential GET-only check. If safe,
reviewed replacement and least-privilege credentials are not available,
**STOP**; do not create another tunnel or silently use a checkout script.
`Collect` remains independently gated and disabled unless the OS proof
exists. A source merge is not a LIVE/credential/installation permission.

Disconnected tests in the existing Makefile cover isolated import guards,
owner grant + external gate consumption, no DB open without RO proof,
and synthetic one-shot injected GET. These tests DO NOT prove real
Cloudflare, client-IP forwarding, or German privacy approval.

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
