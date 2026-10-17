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

## Trusted one-file installer (source-only follow-up, issue #1077)

The installer source is `scripts/install-ausmalwiese-catalog-hide-v1.py`, with offline
regressions in `tests/test-ausmalwiese-catalog-hide-installer-v1.py`.
It is **not installed or executable as a trusted LIVE tool** merely because it
exists in GitHub, and its source merge never triggers installation/unlisting.

The only allowed installed target is
`/usr/local/bin/ausmalwiese-catalog-hide` (root:root, mode `0755`).
The installed operator must match exact pinned Git blob
`a07d95fe78f34b5fc90eaf2eb202eb3a4815259c`, Git source
`ops/bin/ausmalwiese-catalog-hide`, tree mode `100755`.
The installer reads the trusted owner checkout from
`/home/andris/RPi5_main`, using unprivileged `andris` and a
clean Git environment with hooks and optional locks disabled. It checks exact
`main` HEAD given by the caller, clean tracked/untracked state, pinned Git
tree mode and object bytes, including a second source read before installation.
Source checkout code is never executed as root.

Modes (must be invoked via a **separately reviewed trusted execution bridge**
after fresh exact owner approval; examples below are **CLI contract only**, not
instructions to run them from the checkout):

- `--check --expected-rpi5-main-sha <full-main-sha>`: read-only preflight;
  validates root caller identity, `andris` home/checkout identity, pinned
  Git source, fixed root-owned installation path parents, and absence of target.
  No directory or file is created.
- `--apply --expected-rpi5-main-sha <full-main-sha>`: after a fresh equivalent
  preflight, creates only the absent root-owned operator via
  `O_CREAT|O_EXCL|O_NOFOLLOW`, writes pinned bytes, `fsync`, sets mode
  `0755`, verifies inode/owner/mode/bytes, and `fsync`s parent.
  The **first LIVE mutation** is creation of the destination inode.
  A pre-existing file, directory, or symlink is a hard STOP; there is no
  overwrite, repin, upgrade, mode repair, rollback, cleanup or automatic retry.

**Separate owner LIVE decisions required**: (1) authorize trusted installer
bootstrap and this exact one-file installation, bound to current source and
host state; (2) after fresh independent catalogue/sitemap and writer
preflight, authorize the installed hide operator's one-ID `--apply` action.
The installation grant never authorizes unpublishing, and merge never grants
either LIVE action. The shared `flock` alone is not proof of writer quiescence.
No Drive, media, originals, app deployment, services, DNS, Cloudflare, secrets,
or permissions other than the one future new installed file are in scope.
