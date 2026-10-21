# Ausmalwiese admin ZIP publisher v1

Issue: RPi5_main #1149.

## Owner workflow

1. ChatGPT creates approved coloring-page PNG drafts and packages them into one ZIP.
2. The owner opens the protected Ausmalwiese ADMIN page.
3. Upload the ZIP and inspect the private previews/titles.
4. The owner explicitly chooses one canonical category.
5. Press **Veröffentlichung starten**.
6. The browser polls the job status while RPi5 performs print preparation, validation, ID allocation, import, derivatives/catalog update, sitemap refresh when enabled, and public verification.
7. PASS shows each published activity ID and direct `https://ausmalwiese.de/detail.html?id=<id>` link.

The public Ausmalwiese container stays read-only. This service binds only to `127.0.0.1:8765`. The owner-approved canonical external hostname is `admin.ausmalwiese.de`; its Tunnel/DNS route and exact-owner Cloudflare Access protection are separate owner-gated LIVE work.

## ZIP contract

The upload is raw `application/zip`. ZIPs contain 1–20 top-level PNG files only. The service rejects nested paths/traversal, directories, hidden names, duplicate names, encrypted entries, symlinks/special files, non-PNG files, oversized archives/members/uncompressed totals, and excessive compression ratios. It never calls `extractall`; validated members are streamed into generated private staging names.

PNG geometry follows the existing Coloring Pages authoring contract (portrait/landscape, short side >=800 px, long side >=1100 px, accepted A4-like/2:3 ratio).

## Publication boundary

Publication is serialized with the existing Drive ingest lock:
`/srv/coloring-pages-content/state/drive-ingest/.lock`.

The current immutable Coloring Pages image is used for:
- `coloring-pages-print-master prepare`
- `coloring-pages-print-master validate`
- `coloring-pages-import`

New IDs are random seven-digit values and are checked against fresh live catalogue state before import. A prepared master is handed to the existing inbox without overwrite. Each successful import produces the normal private original and public thumb/preview/print derivatives.

After committed imports the installed sitemap publisher is invoked only when its existing reviewed enable marker is present. Sitemap freshness is best-effort, matching the current Drive-ingest behavior; it does not roll back a successful content import.

Final PASS requires local derivative checks plus HTTP 200 for catalog, thumb, preview, print and the detail page.

## Failure model

No automatic retry, rollback, cleanup, overwrite or alternate publication path occurs after production mutation starts. If a later page in a ZIP fails, the job records the exact already-succeeded subset and stops.

## LIVE gates

Source merge does not install, start, route or expose this service. Installation requires a separate exact owner authorization for the reviewed installer. The canonical external ADMIN hostname is `admin.ausmalwiese.de`. Creating its Tunnel/DNS route and exact-owner Cloudflare Access application/policy remains a separate owner gate.
