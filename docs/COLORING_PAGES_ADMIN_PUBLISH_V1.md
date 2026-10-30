# Ausmalwiese admin ZIP publisher v1

Issue: RPi5_main #1149.

## Canonical category and topic selection (#1276)

ADMIN reads exactly the deployed public `https://ausmalwiese.de/categories.json` and
`https://ausmalwiese.de/topics.json` registries. Fixed URLs, schema, unique
IDs, bounded payloads and SHA-256 combined version are enforced before the
protected `GET /api/categories` offers a category plus optional topic.
New deployed registry items appear in the ADMIN menu without duplicated
hard-coded Python or JavaScript category tables. Topic kind is aligned with
the public filtering contract: seasonal topics under `jahreszeiten`, other
topics under other categories. Explicit topic selection (not title inference)
is passed through job state to every ZIP page as importer `--topic`,
and verified in the resulting `catalog.json` entry. Legacy records with no
explicit `topics` remain supported, and edit/archive/restore do not erase them.

**Dependency and rollout status (verified 2026-10-29): satisfied.**
The reviewed `coloring-pages` dependency is source
`e16ccf09e04bff3004a41a87e22e900472cb9e4a` in immutable image
`ghcr.io/rozkalnsandris/coloring-pages@sha256:c6a51aa4ffcf3911e8d4118fbbedfd153e155fe4fcf5a8485ea539d238b9a049`.
It exposes both public category/topic registries and supports importer
`--topic` persistence. The reviewed ADMIN publisher was rolled out from
`RPi5_main@b57a845b4dae5c6184ab78a96979a01616fc8343`; live
`GET /api/categories` returned the canonical German category labels and
topic registry after the bounded taxonomy User-Agent compatibility fix.
The protected ADMIN publisher still rejects unavailable/stale taxonomy or an
incompatible pinned importer **before content mutation**, retaining the print
prepare/validate gate, shared lock and no-retry semantics. This verification
does not authorize an actual ZIP publication or any unrelated LIVE mutation.

## Multiple category ADMIN picker — issue #1281 (source-only)

The public prerequisite is `coloring-pages#432` (merged source
`5d67bd1957ec95fb3aaa185cc930d6ea116f67b2`). The RPi5 public container
was verified by the owner with matching immutable digest
`sha256:080270f8bf7e98bb2da0cfbfd71434238edbf3ce78f6f5ad10e66c87b3e6b777`,
`/health=200`, and `/ready=200`.

At upload Step 3, choose one or more canonical categories. Selected category
chips retain order: the first is the primary `category`, all selected values
appear in ordered `categories[]`. Remove buttons are keyboard accessible and
move focus back to the native selector. Removed categories become available again.
No selection means Publish is disabled. `Topic (optional)` remains independent:
seasonal topics require `jahreszeiten`, evergreen topics require at least one
other category. Removing the only compatible category visibly clears the topic.
Each ZIP PNG receives the same ordered categories in its own one-page activity.

The Catalog and Archive display all selected category labels and the Catalog
filter matches any assigned category. Editing permits category chip changes;
an incompatible previously assigned topic is cleared, while other metadata,
archive snapshots, restore, IDs, assets and legacy single-category records
remain intact. The protected API validates exactly one primary, up to six
distinct canonical IDs, canonical taxonomy SHA-256 and topic compatibility
before job creation and again under the existing shared publication lock.
The importer receives repeated `--additional-category` flags for secondaries.
For each imported ID the catalogue is checked for exactly one matching entry,
the ordered categories and any explicit topic.

**Release gate:** PR #1282 intentionally retained the old ADMIN importer
pin `sha256:c6a51aa4ffcf3911e8d4118fbbedfd153e155fe4fcf5a8485ea539d238b9a049`. Follow-up issue #1283 repins the **source**
to the reviewed `sha256:080270f8bf7e98bb2da0cfbfd71434238edbf3ce78f6f5ad10e66c87b3e6b777` image (public source
`5d67bd1957ec95fb3aaa185cc930d6ea116f67b2`), which exposes repeatable `--additional-category`.
The public RPi5 container digest and /health+/ready were verified by the owner;
that evidence **does not** prove the protected ADMIN publisher is installed.
The runtime still requires a read-only canonical registry and CLI capability
probe **before job creation** and again under the publication lock before
staging/ID allocation. A source commit/merge does not install or restart ADMIN.
Before multi-category publication is considered operational, the exact new
RPi5_main source must be merged, the ADMIN full installer separately authorized
and run with active-job/lock preflight, and runtime identity, readiness and the
pinned importer capability verified. No real ZIP upload, content mutation,
new permissions, retries, rollback or cleanup are authorized by this source change.

## Owner workflow

1. ChatGPT creates approved coloring-page PNG drafts and packages them into one ZIP.
2. The owner opens the protected Ausmalwiese ADMIN page. The admin interface is English, uses the same Baloo 2/Nunito typography as the public Statistics/Traffic dashboards, and provides one header navigation containing Overview, Add pages, Catalog, Archive, Activity, Statistics and Traffic. Below 1200px, the same navigation opens with the Menu button; Escape or choosing a link closes it. The active admin section remains highlighted, including Catalog while editing.
3. Open **Pievienot**, upload the ZIP and inspect the private previews/titles.
4. The owner explicitly chooses one or more canonical categories; the first is primary.
5. Press **Sākt publicēšanu**.
6. The browser polls the job status while RPi5 performs print preparation, validation, ID allocation, import, derivatives/catalog update, sitemap refresh when enabled, and public verification.
7. PASS shows each published activity ID and direct `https://ausmalwiese.de/detail.html?id=<id>` link.

The public Ausmalwiese container stays read-only. This service binds only to `127.0.0.1:8765`. The owner-approved canonical external hostname is `admin.ausmalwiese.de`; its Tunnel/DNS route and exact-owner Cloudflare Access protection are separate owner-gated LIVE work.

## Admin navigation

The protected single HTML document provides separate addressable screens. Hash routes work on the existing root handler without new service routes, ingress changes or a framework:

| Address | Screen |
| --- | --- |
| `/#overview` (default) | Overview with catalogue/archive counts and shortcuts |
| `/#upload` | ZIP upload, previews, category selection and publication progress |
| `/#catalog` | Search, category filter and 24-entry catalogue pages |
| `/#edit/<encoded-id>` | Dedicated editor with thumbnail, metadata form and public-page link |
| `/#archive` | Restore and existing guarded permanent-delete actions |
| `/#activity` | Seven-day activity log |
| `/#stats` | Engagement, QR, campaign counters and page rankings |
| `/#traffic` | Traffic, Instagram attribution, views and crawler summaries |

All screens use one admin navigation, public-site link, Nunito body text and Baloo 2 display typography. Statistics and traffic are native hash routes in this same shell. The layout takes inspiration from [Tabler](https://tabler.io/) task navigation and compact content lists; no template code, Bootstrap dependency or new runtime asset is added.

Search/category/page state and staged upload titles survive section changes within the document. Browser back/forward and direct editor links select the correct screen. Leaving a dirty editor requires confirmation; leaving/reloading the document also warns about an unsubmitted upload or active publication. An active job is linked from every screen and retains the existing reload recovery/polling flow.

The editor freezes its catalogue ETag when the fields are populated. A 412 preserves the draft, displays a focused error and disables resubmission until the owner opens a fresh editor from the catalogue. Background catalogue reads cannot silently rebase an edit. Publication status messages are separate from catalogue errors.

Validation: `python3 tests/test-coloring-pages-admin-publish-v1.py` includes offline Node.js behavioral checks in `tests/test-coloring-pages-admin-navigation.cjs`; Node uses only built-in modules. Browser validation should use local synthetic API fixtures for navigation, save, stale-write and responsive checks. No production mutations are needed to review the interface.

UI source changes do not deploy themselves. Use the existing separately authorized UI-only installation path after review/merge; no service/API/authentication change is part of this navigation update.

## ZIP contract

The upload is raw `application/zip`. ZIPs contain 1–20 top-level PNG files only. The service rejects nested paths/traversal, directories, hidden names, duplicate names, encrypted entries, symlinks/special files, non-PNG files, oversized archives/members/uncompressed totals, and excessive compression ratios. It never calls `extractall`; validated members are streamed into generated private staging names.

The ZIP is a **draft handoff**, not a print-master package. It contains no JSON manifest, category metadata, publication ID, preview, thumbnail, checksum file, PDF or other member. Filenames provide only the editable initial title shown in ADMIN. The owner chooses the canonical category in the protected UI.

PNG geometry follows the existing Coloring Pages authoring contract (portrait/landscape, short side >=800 px, long side >=1100 px, accepted A4-like/2:3 ratio). Each PNG in ADMIN v1 is one independent single-page activity; the ZIP does not encode ordered multi-page activity identity.

## Publication boundary

Publication is serialized with the existing Drive ingest lock:
`/srv/coloring-pages-content/state/drive-ingest/.lock`.

The current immutable Coloring Pages image is used for:
- `coloring-pages-print-master prepare`
- `coloring-pages-print-master validate`
- `coloring-pages-import`

The ADMIN source pin targets reviewed application source `5d67bd1957ec95fb3aaa185cc930d6ea116f67b2` and immutable image `ghcr.io/rozkalnsandris/coloring-pages@sha256:080270f8bf7e98bb2da0cfbfd71434238edbf3ce78f6f5ad10e66c87b3e6b777`. The pinned image includes the canonical public category/topic registries, importer `--topic` persistence (#1276), and repeated `--additional-category` (#1281). This is a source-state statement, **not** evidence that the protected RPi5 ADMIN service has been updated; separately authorized guarded LIVE installation and verification remain required.

### Mandatory print-quality gate

Every uploaded PNG is an authoring draft. Before any publication ID allocation or import, the ADMIN job must complete this exact fail-closed order for the whole ZIP:

1. run `coloring-pages-print-master prepare` for every uploaded PNG;
2. run `coloring-pages-print-master validate` for every prepared PNG;
3. require `VALIDATE_PRINT=PASS` for every prepared page;
4. only then allocate IDs and begin import.

The prepared publication master must satisfy the canonical Coloring Pages media contract:

- exact `2480×3508` portrait or `3508×2480` landscape A4 raster;
- RGB with no alpha;
- approximately 300×300 DPI metadata;
- exact `#FFFFFF` complete outer page border;
- complete 15 mm / 177 px exact-white artwork-safe bands on every edge;
- source aspect ratio preserved and artwork centered in the safe area;
- transparency composited onto white;
- near-neutral AI whites normalized to exact white;
- Pillow LANCZOS resampling;
- only the reviewed conservative UnsharpMask sharpening.

Any prepare or validate failure is a STOP **before ID allocation/import**. The prepared master SHA-256 and exact byte size are recorded only after validation PASS.

This technical gate does not determine editorial quality. Wrong anatomy, wrong wording, unwanted decoration, non-coloring artwork or other visual defects remain the Chat/owner review responsibility before ZIP upload.

New IDs are random seven-digit values and are checked against fresh live catalogue state **and every valid ADMIN archive/tombstone ID** before import. This prevents reuse of permanently deleted IDs. A prepared master is handed to the existing inbox without overwrite. Each successful import produces the normal private original and public thumb/preview/print derivatives.

After committed imports the installed sitemap publisher is invoked only when its existing reviewed enable marker is present. Sitemap freshness is best-effort, matching the current Drive-ingest behavior; it does not roll back a successful content import.

Final PASS requires local derivative checks plus HTTP 200 for catalog, thumb, preview, print and the detail page.

## Failure and recovery model

No automatic retry, requeue, rollback, cleanup, overwrite or alternate publication path occurs after production mutation starts. If a later page in a ZIP fails, the job records the exact already-succeeded subset and stops.

The ADMIN browser persists only the active `job_id` in same-tab `sessionStorage`. Reloading the tab restores that server-side job and resumes status polling; the ZIP bytes and publication state remain server-side. If browser status polling hits a transient fetch/Access/network error, the UI keeps the current job visible and retries with bounded exponential backoff up to 10 seconds instead of permanently stopping after the first failed poll.

The backend exposes `GET /api/jobs/active` for recovery when the same-tab key is unavailable. A POST that encounters one genuinely active job restores/returns that job instead of creating a second publication. The shared `fcntl.flock(... LOCK_EX|LOCK_NB)` remains the authoritative publication serialization boundary and is not weakened.

At service startup, any persisted job still marked `queued` or `running` belongs to a previous process lifetime and is fail-closed to terminal `failed` with `interrupted=true` and source-controlled error `publication interrupted by service restart`. Existing `results` are preserved byte-for-byte in job state and rendered in the UI as the partial succeeded subset so the owner can see already imported/published IDs and avoid accidental duplicates. Startup reconciliation never retries, requeues, deletes, rolls back or cleans up content.

## Diagnostic logs

The ADMIN service writes privacy-bounded structured diagnostics to:

```text
/srv/coloring-pages-content/state/admin-publish/logs/admin-publish.log
```

The log directory is owned by `andris:andris` with mode `0700`; log files are mode `0600`. Python stdlib `logging.handlers.TimedRotatingFileHandler` rotates at UTC midnight. Rotation uses daily files, while explicit age pruning removes only files matching `admin-publish.log` or `admin-publish.log.YYYY-MM-DD` once they are older than seven days. Pruning runs at startup and around normal log emission so an idle service cannot retain stale ADMIN diagnostics indefinitely. No global `journald` retention setting is changed.

Allowed log metadata is bounded to diagnostic identifiers and timings: UTC timestamp, severity, event, process id, job/upload id, page index/count, step name/status/duration, tool name, timeout/exit status, allocated public page id, sitemap/public-verification phase, terminal job status, stale-job reconciliation and partial result count.

The logger never records request/response bodies, HTTP headers, cookies, Cloudflare Access identity/tokens, credentials/secrets, environment variables, ZIP/PNG bytes, raw file contents, wholesale subprocess stdout/stderr or unsanitized tracebacks. Logging initialization is fail-closed before the service accepts publication jobs; a safely initialized diagnostic log is therefore part of the ADMIN runtime preflight, not an optional debug side channel.

## Catalogue management extension (issue #1172)

The same protected ADMIN service also provides a minimal catalogue manager. This deliberately reuses the existing loopback listener, Access boundary, publication lock, diagnostics and installer instead of introducing a database, framework, second service or second port.

### Catalogue read model

`GET /api/catalog` reads the current LIVE `catalog.json` and returns only fields needed by the ADMIN UI. The response includes a strong SHA-256 validator as both `catalog_sha256` and an HTTP `ETag`. The browser must reload before a mutation whenever that validator changes.

### Metadata edit

`POST /api/catalog/edit` may change only:

- `title`;
- `category`;
- `age`;
- `difficulty`.

The request must include the exact current catalogue validator through `If-Match`. Server-side validation enforces exact request keys, valid catalogue ID syntax, the canonical category allowlist, allowed age/difficulty values and the existing bounded Unicode title rule. A stale validator fails with HTTP 412 before mutation.

The service acquires the same shared publication lock used by publication before any catalogue write. This prevents an ADMIN metadata edit from racing a publication/import operation. The candidate catalogue is written to a same-directory exclusive temporary file, fsynced, atomically replaced with `os.replace`, then hash-verified.

### Reversible archive / restore (issue #1174)

`POST /api/catalog/archive` replaces the former one-way unpublish action. The owner must type the exact activity ID as confirmation and provide the current catalogue `If-Match` validator.

Before the catalogue entry is removed, the service writes a private owner-only archive record under:

`/srv/coloring-pages-content/state/admin-publish/archive/<id>.json`

The archive directory is mode `0700`; records are mode `0600`. A record contains the complete catalogue entry needed for restoration, timestamps and catalogue hash provenance, but never copies media/original bytes.

Archive state is fail-safe and explicit:

1. `prepared` — the restorable record is persisted before catalogue removal;
2. `archived` — catalogue removal completed and the new catalogue hash is recorded;
3. `restored` — restoration completed; the same archive record cannot be restored again.

A `prepared` record whose ID is absent from the live catalogue remains restorable if the final state-marker write was interrupted. A duplicate archive record for an ID is rejected instead of overwritten.

`GET /api/archive` returns only active restorable records and safe catalogue-display fields.

`POST /api/catalog/restore` requires the same exact-ID confirmation and current `If-Match`. Restore is rejected if the ID already exists live, the archive state is not restorable, or the archived title/category/age/difficulty no longer passes current validation. Successful restore atomically writes the catalogue, marks the private archive record `restored`, and runs the existing best-effort sitemap refresh.

Archive/restore never deletes or rewrites:

- public media files;
- private originals;
- inbox or receipts;
- Drive files;
- analytics/engagement data.

Physical media/original deletion is available only through the separate guarded archive-delete contract below.

### Guarded permanent delete (issue #1178)

Permanent Delete is intentionally available **only after a completed archive**. It is not a live-catalog action and it is not a bulk action.

The browser sends `POST /api/archive/delete` with:

- the exact activity ID;
- a second exact-ID confirmation;
- the literal confirmation phrase `DELETE`;
- the current strong catalogue validator through `If-Match`.

The backend acquires the same shared publication/catalogue lock, re-reads the current catalogue, requires the ID to be absent, and requires the private archive record to be exactly in `archived` state.

Before the first file deletion it validates the complete physical target set. Only these paths are eligible:

- `/srv/coloring-pages-content/originals/<id>/`;
- `/srv/coloring-pages-content/public/media/<id>/`;
- `/srv/coloring-pages-content/inbox/<id>.png`, only when that exact regular file exists.

The originals/media targets must be exact direct-child directories under their canonical roots, not symlinks, owned by the ADMIN runtime user, and contain direct regular files only. The delete inventory is bounded to at most 128 files and 1 GiB total. Nested directories, symlinks, special files, owner drift, inode/path drift or target-content drift fail closed.

The archive lifecycle extends with:

1. `archived`;
2. `delete-prepared` — persisted **before** any physical file mutation, with bounded counts/bytes only;
3. `deleted` — terminal tombstone after all exact-ID production files are gone.

Once `delete-prepared` exists, automatic restore and another delete attempt are forbidden. The ADMIN UI keeps that item visible as interrupted/manual-review state. There is no automatic retry, rollback, cleanup, second delete pass or alternate mutation path.

A successful delete keeps the private `deleted` tombstone permanently. It is hidden from the normal archive list, but its ID stays reserved. ADMIN ID allocation now excludes every valid archive/tombstone ID as well as every current catalogue ID, so a permanently deleted ID cannot later be randomly reused.

Permanent Delete does **not** remove or rewrite:

- `catalog.json` (the item was already archived and absent);
- archive/tombstone metadata;
- upload/job history;
- diagnostic logs;
- analytics/engagement data;
- Drive files or receipts;
- unrelated inbox/media/original paths.

The sitemap does not need another mutation here because the catalogue item was already removed during Archive.

### Browser mutation security

All state-changing ADMIN requests are POST-only and require:

1. the existing `X-Ausmalwiese-Admin: 1` marker;
2. a per-process 256-bit in-memory CSRF token obtained through same-origin `GET /api/session` and sent in `X-Ausmalwiese-CSRF`;
3. Fetch Metadata that is not cross-site when the browser supplies it;
4. an allowed `Origin` when the browser supplies one.

The public ADMIN route must remain protected by exact-owner Cloudflare Access. SameSite cookies are defense-in-depth; they do not replace the application mutation checks above. The service does not emit CORS allow headers.

The ADMIN HTML also emits deny-framing, no-referrer, no-sniff, restrictive permissions policy and a same-origin Content Security Policy compatible with the current single-file UI.

### Audit trail and activity view

Successful catalogue edits, archive and restore actions are recorded in the existing private seven-day ADMIN diagnostic log using bounded metadata only: activity ID, action, archive state, changed field names and catalogue SHA-256 before/after. Request bodies, titles, HTTP headers, cookies, Access identity/tokens, credentials and raw catalogue contents are not logged.

Issue #1174 adds `GET /api/activity`, a read-only sanitized view over those existing seven-day log files. It never returns raw log lines. The service accepts only the logger's known field set, then exposes a smaller presentation allowlist. Any malformed JSON, unexpected field, unsafe type or overlong value fails closed. Reading is bounded to 2 MiB per log file, 4 MiB total and at most 200 newest events. The endpoint does not delete logs or change retention/journald settings.

### Simple deployment boundary

Issues #1172 and #1174 add no deployment mechanism. Backend changes reuse the existing guarded `full` installer and therefore require a later separately authorized SSH/runtime install and service restart. The `ui-only` mode is insufficient for this extension because the backend API changes too. Source merge itself never installs or restarts the ADMIN service.

Security references used for this design:

- OWASP CSRF Prevention Cheat Sheet;
- OWASP REST Security Cheat Sheet;
- OWASP Input Validation Cheat Sheet;
- OWASP Logging Cheat Sheet;
- RFC 9110 conditional requests / `If-Match`;
- Cloudflare Access authorization-cookie documentation;
- Python `http.server` security warning. The stdlib server remains acceptable here only inside the existing loopback + exact-owner Access boundary; it must not be exposed directly.

## Safe ADMIN updates

The reviewed installer has two explicit modes.

- `full` is the runtime install/update path. If the ADMIN service is already active, the installer must acquire the shared publication lock and require `GET /api/jobs/active` to report idle before the first installed-file mutation. A busy publication lock, an active queued/running job, an unreadable/invalid status response, or any uncertainty is a STOP before install or restart. A successful full update restarts the service only after that preflight. After `systemctl is-active` succeeds, the installer gives the local root endpoint one bounded readiness window: up to 10 attempts, each capped at 0.25 s, with 0.25 s between failed attempts, for a worst-case window of 4.75 s. HTTP success ends the wait; exhaustion is a terminal installer failure and does not trigger a second restart or installer retry.
- `ui-only` replaces only the static ADMIN `index.html`. It requires the service to be active and the installed font files to match their pinned hashes. It performs no `daemon-reload` and no service restart, so routine HTML/navigation changes do not interrupt publication jobs.

Neither mode retries, requeues, rolls back or cleans up publication state. The `ui-only` confirmation token is deliberately distinct from the full publisher-install confirmation so a static update cannot silently widen into a runtime restart.

## One-command guarded SSH deploy (issue #1176)

The ADMIN service deliberately does **not** become a generic SIMPLE-DEPLOY Compose target. SIMPLE-DEPLOY v1 is image/Compose based and explicitly forbids arbitrary shell/argv and unrelated systemd mutation. Widening that shared executor to run a host installer would weaken its trust boundary.

Instead, issue #1176 adds one target-bound wrapper:

`scripts/deploy-ausmalwiese-admin-v1.py`

It accepts only:

- `--expected-source-sha <40-lowercase-hex>`;
- `--apply`.

The wrapper requires root, exact clean `main`, the exact GitHub origin, and HEAD equal to the supplied SHA. It then invokes the reviewed full installer exactly once with its fixed confirmation token and `full` mode. It does not accept arbitrary command, path, environment, installer mode or extra argv input.

All mutation safety remains owned by the existing installer: shared publication lock, active-job idle check, exact clean checkout, one restart/start path and bounded readiness window.

After a successful installer exit, the wrapper performs read-only local verification only:

- `coloring-pages-admin-publish.service` is active;
- `GET http://127.0.0.1:8765/` succeeds;
- `GET /api/catalog` has a valid count/list/SHA-256 model;
- `GET /api/archive` has a valid count/list/catalog-hash model;
- `GET /api/activity` has a valid bounded count/list model.

Any failure after the installer starts is terminal for that attempt: no automatic retry, rollback, cleanup, second restart or alternate execution path.

Source merge never runs this wrapper. A later SSH apply still requires separate exact owner LIVE authorization for the ADMIN install/restart target.

## LIVE gates

Source merge does not install, start, route or expose this service. Installation or a UI-only update requires a separate exact owner authorization for the reviewed installer mode. The canonical external ADMIN hostname is `admin.ausmalwiese.de`. Creating its Tunnel/DNS route and exact-owner Cloudflare Access application/policy remains a separate owner gate.

## Latvian font coverage

The admin keeps the public site's Baloo 2 and Nunito variable families. Latin
Extended faces supplement the original Latin subsets, with explicit Unicode
ranges so Latvian accented letters use the same family and weight.

Both additional WOFF2 files come from the same Fontsource revision as the public
site's Latin files:
`fontsource/font-files@c3f4e3e5a664d2c3002e800050ce809a790d7281`.

| Family | Upstream path under `fonts/variable/` | SHA-256 |
| --- | --- | --- |
| Baloo 2 | `baloo-2/files/baloo-2-latin-ext-wght-normal.woff2` | `dfd52ee2e67ff597c9a47238d59adcee2b27d8adf9245e2d53a46dd73db99dde` |
| Nunito | `nunito/files/nunito-latin-ext-wght-normal.woff2` | `2c8d792869818ecb253a46bc3c63c7013df7aac2f69291c3c85e5cdc94160960` |

Upstream licenses are the SIL Open Font License 1.1 in each family's
`LICENSE` file at that revision. Assets are not bundled in this repository;
the installer downloads exact pinned bytes and verifies both hashes before
installing any source. Browsers load all fonts from the admin origin; CSP is
unchanged.

The first rollout needs the existing separately authorized **full** installer,
because it adds two files and two allowlisted backend routes. `ui-only` fails
before replacing HTML unless the extended files and served hashes already
match. Full mode verifies all four font responses after readiness. The deploy
wrapper budget is 90 seconds to accommodate the two additional bounded downloads.
Source merge alone does not deploy this change.



## Native analytics in the admin shell (#1190)

The protected admin UI now includes `#stats` (Statistics) and `#traffic`
(Traffic) alongside the existing routes. Every screen uses the same header,
English text and self-hosted Latin/Latin Extended fonts. The root reserves a
stable scrollbar gutter, with an always-visible scrollbar fallback, so the empty
archive does not shift navigation relative to the longer catalog.

The native dashboards preserve engagement/QR counters, Dortmund campaign funnel,
Popular/Trending, traffic/views, Instagram 7/30-day attribution, crawler summaries,
and searchable/sortable page tables with 20-row pagination. Data is loaded only
when opening an analytics route; Refresh obtains a new snapshot. Public page
links open separately, keeping the admin route available. Missing capabilities
show a dash. Failed core reads hide the old snapshot; optional campaign/traffic
failures keep available counters and explicitly mark unavailable data.

### Fixed read-only adapter

The existing admin service reads only these exact upstream aggregate endpoints
on `https://ausmalwiese.de`, using the descriptive `Ausmalwiese-Admin/1.0` agent:

| Admin endpoint | Upstream |
| --- | --- |
| `/api/analytics/overview` | `/api/stats/overview` |
| `/api/analytics/traffic?days=7` | `/api/stats/traffic?days=7` |
| `/api/analytics/campaigns?days=7` | `/api/stats/campaigns?days=7` |
| `/api/analytics/campaigns?days=30` | `/api/stats/campaigns?days=30` |

No arbitrary query, URL, method, incoming credential or cookie is forwarded.
Redirects are refused; each upstream read has a 10-second socket timeout and a
4 MiB response ceiling. Only successful JSON with the expected top-level shape
is returned. Errors are sanitized to a 502 response, and admin responses remain
`no-store`. Browser reads time out after 15 seconds. The CSP remains same-origin
for scripts and API connections. There is no analytics database or tracking
write in the admin application, and no Worker/D1, Access, DNS or Tunnel change.
Existing Access protection for the admin host remains the deployment boundary.
Existing public dashboard URLs remain compatible.

UI and metric semantics were adapted from `rozkalnsandris/coloring-pages` at
`a910b39a7a8617c1589069a12b0c7c2243b26543` (`stats.html`, `traffic.html`,
`js/stats-admin.js`, `js/traffic-admin.js`, `css/app.css`). The visitor-tracking
client `js/stats.js` is deliberately not included.

### Rollout and verification

The first release of this integration requires the existing **full admin
installer**, including the backend update and its single service restart, under
separate exact owner LIVE authorization. `ui-only` refuses an old backend before
writing HTML by checking `/api/analytics/capabilities` version 1/read-only true.
A source merge does not perform this rollout.

After an authorized deployment, verify the exact installed HTML/backend source,
service health, capabilities and all four read-only endpoints, then open both
analytics hash routes in the authenticated browser. Compare catalog/archive
header coordinates and desktop/mobile navigation. Do not change Access policy or
copy credentials if an upstream read is unavailable; surface the bounded error
and preserve the existing protection.

Offline validation: `python3 tests/test-coloring-pages-admin-publish-v1.py`
(includes both Node behavioral suites). Tests cover fixed request destinations,
query rejection, redirect refusal, size/schema/error bounds, lazy/deep navigation,
dirty-edit guards, search/pagination, missing capabilities, text-only rendering
of untrusted labels, and stale-data hiding after a failed refresh.


### English admin interface

The owner requested English for the entire combined admin panel, including
Statistics and Traffic. All navigation, headings, controls, help text, empty and
error states, progress labels, confirmation dialogs, accessibility labels and
browser titles use English. Dates and aggregate numbers use `en-GB`; the page
language is `en`. Catalog titles and other owner-entered content retain their
original language. Existing Latin Extended font support remains available for
those titles. Restore and Refresh remain distinct actions; the exact `DELETE`
confirmation and all existing mutation guards remain unchanged.
