# Ausmalwiese one-ID catalogue hide — source-only v1

**Frozen scope:** one published learning activity, `9444491`, German title
`Roboter zum Ausschneiden und Zusammensetzen`. The faulty cutout sheet already
has a pair of eyes on its head and a second pair as cutout pieces. Owner requests
unlisting, **not** media erasure or an in-place image overwrite.

## Reviewed candidate, not yet installed

- Source: `ops/bin/ausmalwiese-catalog-hide` (Python standard library only).
- Target: exactly `/srv/coloring-pages-content/public/catalog.json` and
  `/srv/coloring-pages-content/public/sitemap.xml` on `rpi5`.
- Existing serialization/URL origin is preserved where possible; sitemap must
  match the catalogue's complete sorted URL list before the change. Accept only
  `https://ausmalwiese.de` or legacy `https://coloring.rozkalns.net` if already
  present; **never** silently change canonical domain during this correction.
- Preserve remaining catalogue record order and fields. Preserve remaining
  sitemap XML lines verbatim. Exactly one record and URL disappear. No `media/`,
  originals, inbox, receipts, backup, analytics, engagement data or Drive files
  are touched. Existing direct media URLs are **not** blocked/deleted; this is
  unlisting only, not guaranteed erasure/410.
- The operator is **not installed**, callable from LIVE or triggered by merge.
  No install helper, timer, Cloudflare update or importer wiring is included.

## Proposed gated procedure (future separately authorized LIVE)

1. Freeze exact `RPi5_main` merge SHA and reviewed installed operator Git blob;
   independently verify the trusted installation mechanism, file ownership and
   operator identity; do not execute a raw source checkout on LIVE as a shortcut.
2. Confirm quiescence of **all** catalogue and sitemap writers (the shared Drive
   ingest lock is advisory only); validate `andris` unprivileged execution,
   fixed path owner/modes, regular non-symlink files, target ID/title/category,
   exactly one matching record, complete catalogue↔sitemap consistency and no
   left-over stages. Check the public origin and local HTTP routing separately.
3. Run installed `--check` (read-only); freeze SHA-256 of the exact current
   catalogue and sitemap, plus output SHA-256 candidates and counts.
4. Seek a fresh owner LIVE authorization binding host, installed blob/main SHA,
   target ID, both exact baseline digests, writer exclusion and one bounded
   two-file update. `--apply` requires both exact hashes as CLI inputs. This
   source approval and a future merge grant **no** host mutation authority.
5. Inside the same existing `state/drive-ingest/.lock` exclusive flock: verify
   both baselines; create both candidates with `O_EXCL|O_NOFOLLOW` in the public
   directory; fsync; verify candidate bytes and unchanged baselines; atomically
   replace **sitemap first**, then catalogue; fsync and verify local HTTP byte
   equality (127.0.0.1:9191). Afterward separately verify public
   `https://ausmalwiese.de/catalog.json`, sitemap and detail-page fallback.

**First production mutation:** creation of
`.catalog.json.hide-9444491.partial`. On any error thereafter, **STOP** and
preserve exact evidence; no automatic retry, rollback, deletion of temporary
files, alternate execution, source checkout install, or second mutation.
A failure between replacements may leave a sitemap/catalogue discrepancy that
requires a **new owner decision** after read-only diagnosis. A previous stale
sitemap, unsupported origin, changed title or an already-unlisted ID is a STOP.

## Offline regression proof

`python3 tests/test-ausmalwiese-catalog-hide-v1.py` exercises exact target
binding, catalogue order/preservation, both origin variants, sitemap validation,
stale hashes, lock contention, stage collision, symlinks, partial replacement
and post-apply verification failure. Tests use `tempfile` only and do **not**
read or write any production path.

## Not part of this authorization

No install, LIVE catalogue edit, sitemap publication, service restart, deploy,
merge, media/original deletion, CDN purge, Cloudflare setting, robots rule or
HTTP 410. Later an optional corrected replacement artwork may be published as
**a new separately approved ID**, not overwrite `9444491`.
