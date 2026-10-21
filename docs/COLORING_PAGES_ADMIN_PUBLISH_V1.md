# Ausmalwiese admin ZIP publisher v1

Issue: RPi5_main #1149.

## Owner workflow

1. ChatGPT creates approved coloring-page PNG drafts and packages them into one ZIP.
2. The owner opens the protected Ausmalwiese ADMIN page. The admin interface is Latvian, uses the same Baloo 2/Nunito typography as the public Statistics/Traffic dashboards, and provides top navigation between Admin, Statistics and Traffic.
3. Upload the ZIP and inspect the private previews/titles.
4. The owner explicitly chooses one canonical category.
5. Press **Sākt publicēšanu**.
6. The browser polls the job status while RPi5 performs print preparation, validation, ID allocation, import, derivatives/catalog update, sitemap refresh when enabled, and public verification.
7. PASS shows each published activity ID and direct `https://ausmalwiese.de/detail.html?id=<id>` link.

The public Ausmalwiese container stays read-only. This service binds only to `127.0.0.1:8765`. The owner-approved canonical external hostname is `admin.ausmalwiese.de`; its Tunnel/DNS route and exact-owner Cloudflare Access protection are separate owner-gated LIVE work.

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

The ADMIN pin is bound to reviewed application source `798b263671c81b4e034b163b263dce7dc18306eb` and immutable image `ghcr.io/rozkalnsandris/coloring-pages@sha256:5e63d5c37807cd25ef3ff384ea6e0681fa5b6995b0d8eb2a5846e038327e4cb4`. That release includes the balanced lossless WebP encoder setting used by the importer.

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

New IDs are random seven-digit values and are checked against fresh live catalogue state before import. A prepared master is handed to the existing inbox without overwrite. Each successful import produces the normal private original and public thumb/preview/print derivatives.

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

## Safe ADMIN updates

The reviewed installer has two explicit modes.

- `full` is the runtime install/update path. If the ADMIN service is already active, the installer must acquire the shared publication lock and require `GET /api/jobs/active` to report idle before the first installed-file mutation. A busy publication lock, an active queued/running job, an unreadable/invalid status response, or any uncertainty is a STOP before install or restart. A successful full update restarts the service only after that preflight.
- `ui-only` replaces only the static ADMIN `index.html`. It requires the service to be active and the installed font files to match their pinned hashes. It performs no `daemon-reload` and no service restart, so routine HTML/navigation changes do not interrupt publication jobs.

Neither mode retries, requeues, rolls back or cleans up publication state. The `ui-only` confirmation token is deliberately distinct from the full publisher-install confirmation so a static update cannot silently widen into a runtime restart.

## LIVE gates

Source merge does not install, start, route or expose this service. Installation or a UI-only update requires a separate exact owner authorization for the reviewed installer mode. The canonical external ADMIN hostname is `admin.ausmalwiese.de`. Creating its Tunnel/DNS route and exact-owner Cloudflare Access application/policy remains a separate owner gate.
