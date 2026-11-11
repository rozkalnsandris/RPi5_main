# Ausmalwiese sitemap: category landing generator upgrade

Issue: #1094. Source-only candidate; no standing LIVE permission.

Consumer source is `coloring-pages@43691b7267d2a8185f3466667f0cdf2b380fbe04`.
The required byte-identical generator is Git blob
`5d1d37c32573aa8ac0d91f45b73938638fd183e9`.

The exact installed predecessor observed before this source change is:
- publisher `7b0330f30e27d6fe9c5f3e4fbf81fc6473ade660`;
- generator `49c8ba34cf0a4c4ab100463df9adacc4c6e90c2c`.

The reviewed successor is:
- publisher `4ade38f1225f4c1bc102fda8d5538f9262695d43`;
- generator `5d1d37c32573aa8ac0d91f45b73938638fd183e9`.

The publisher validates exactly eight static canonical URLs before sorted
catalogue detail URLs: home, `/kita`, and the six existing category routes
`/tiere`, `/fahrzeuge`, `/alphabet`, `/lernen`, `/figuren`,
`/jahreszeiten`.

## Exact upgrade contract

`scripts/upgrade-coloring-pages-sitemap-publisher-v1.py` accepts only the
predecessor pair above and only the reviewed successor pair. It uses fixed
installed targets, the existing Drive-ingest advisory lock, root-owned
publisher/generator modes, exact tracked Git blobs and a clean exact-main
checkout.

Both successor files are staged and fsynced before replacement. The generator
is replaced first and the publisher second. This is intentionally **not** a
transactional two-file swap. Python documents `os.replace()` as atomic on
success when source and destination are on the same filesystem, but there is
still an observable mixed-version interval between the two replacements.
Linux `flock` is advisory, so a future LIVE gate must independently quiesce
all catalogue/sitemap writers for the full operation.

References:
- https://docs.python.org/3/library/os.html#os.replace
- https://man7.org/linux/man-pages/man2/flock.2.html

The existing post-publish activation marker may be either absent or present.
If present, the executor requires the exact root-owned `0444` regular file
with bytes `coloring-pages-sitemap-post-publish-v1\n`, preserves it without
modification, and fails closed if its state changes during the upgrade.

The first stage-file creation is the first LIVE mutation. Any later error is
STOP with evidence preserved: no retry, rollback, cleanup, unlink, permission
repair, service restart or alternate path.

## Deliberate predecessor boundaries

The historical first-install-only installer and the Drive-ingest post-publish
trust pins remain on the predecessor publisher/generator release in issue
#1094. They are **not** upgraded by this source scope. Therefore a later LIVE
publisher/generator upgrade does not itself authorize or silently update the
Drive-ingest operator. A separate source/LIVE decision is required before
post-ingest automatic sitemap refresh can trust the successor pair.

## Next gates

After merge, any host replacement requires a fresh exact LIVE authorization
bound to the merged RPi5_main SHA, installed predecessor blobs, marker/lock
state and no-retry semantics. Sitemap publication is a later separate LIVE
gate with fresh catalogue and prior-sitemap SHA-256 values.

---

## Current source-only SEO successor: issue #1456 (2026-11-11)

The section above documents the **historical #1094 upgrade** and its then-reviewed
release. The reviewed `coloring-pages` source now differs:
`coloring-pages/main@a44f07ebe0dcf9c33efcde8f05c2fa528479c26d`,
merged PR #482, exact upstream generator blob
`f4ffaa4293f9c46f475f96d4409f05ff347a7590`.
The source handoff `deploy/sitemap-publication-handoff-v1.json` specifies
**10 ordered static canonical URLs** (root, Kita, Tiere, Fahrzeuge, Alphabet,
Lernen, Figuren, Jahreszeiten, Essen & Natur, `/kalender.html`),
then the deterministic catalogue-backed detail IDs. Both newly requested
URLs are existing public pages with their own canonical links; no runtime
catalogue, IDs, media or routing change is required.

For the newly pinned fixed-path upgrade script, the **predecessor** is exactly:

- publisher `4ade38f1225f4c1bc102fda8d5538f9262695d43`;
- generator `5d1d37c32573aa8ac0d91f45b73938638fd183e9`.

The **source successor** is exactly:

- publisher `3263845045f6d38f31ff359158be90ab59006240`;
- generator `f4ffaa4293f9c46f475f96d4409f05ff347a7590`.

The new publisher checks the same strict, ordered, single-source URL set and
the exact generator blob. The existing exact-upgrade procedure retains its
staged two-file replacement, nonblocking Drive-ingest advisory lock, root
owner/mode checks, frozen exact-main checkout, marker-state checks, fsync,
old/new SHA guards and fail-closed handling. `os.replace()` is atomic for
**each file**, not for the pair: independent writer quiescence must be verified
before any separately owner-authorized LIVE upgrade.

**Important separate trust boundary:** `ops/bin/coloring-pages-drive-ingest`
and the historical first-install-only installer remain pinned to their
older release. They are **not** changed or enabled in this source scope.
If the post-ingest marker is enabled, the old ingest trust pin will reject
the newer publisher/generator and report a stale sitemap after content
publication; a separate reviewed source and owner LIVE decision is required
to upgrade that trust. Do not assume marker absence from GitHub. A
read-only verification of the installed operator/generator, marker, shared
lock, and all catalogue writers is required before a future host action.

This issue does **not** install/restart services, update production
`sitemap.xml`, rewrite the catalogue, submit Search Console, modify
Cloudflare, or authorize automatic post-ingest sitemap updates. The two
remaining LIVE decisions are separate: (1) exact fixed-path two-file upgrade,
(2) one-shot sitemap publication bound to a fresh catalogue SHA-256 and prior
sitemap SHA-256. A static source merge does not perform either mutation.
The previously observed 477 detail URLs would yield 487 entries if unchanged;
do not treat this conditional count as a current protected-runtime baseline.

Official references:
- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- https://docs.python.org/3/library/os.html#os.replace
- https://man7.org/linux/man-pages/man2/flock.2.html

---

## SEO follow-up: post-publish Drive ingest trust source #1458 (2026-11-11)

The **source-only** `ops/bin/coloring-pages-drive-ingest` post-ingest trust pins
now match the reviewed ten-static-URL publisher/generator pair:

- fixed installed publisher `/usr/local/bin/coloring-pages-sitemap-publish`:
  Git blob `3263845045f6d38f31ff359158be90ab59006240`;
- fixed installed generator
  `/usr/local/share/coloring-pages/coloring-pages-sitemap`:
  Git blob `f4ffaa4293f9c46f475f96d4409f05ff347a7590`;
- resulting **source** Drive ingester Git blob:
  `c4e2f67e0154f705e2d46db9dcc87e6a69b108fd`.
  The previously installed/source ingester was
  `b10dc43bceb8ac3b77d8af47661b11a4ca50ea90`.

Only the two `SITEMAP_OPERATOR_BLOB` and `SITEMAP_GENERATOR_BLOB`
constants change in the Drive ingester. A valid root-owned `0444` marker
with exact bytes `coloring-pages-sitemap-post-publish-v1\n` is **still**
required, and the reviewed Git blobs must match **both** installed files.
There is no fallback trusting old or mixed binary pairs. The same
after-new-ingest-receipt, after-lock-release, no-timer `--check` then
single SHA-guarded `--apply` semantics and fail-closed `STALE` status
remain unchanged.

**Critical LIVE ordering:** the last authorized read-only host inspection
found the marker already enabled, while installed ingester and publisher/
generator were still the predecessor pair. Neither this source merge nor the
existence of that marker grants permission to install or start using new
binaries. A two-file publisher/generator upgrade, an **independent**
Drive-ingester source-to-installed update, and a one-shot sitemap publish
each cross separately authorized LIVE boundaries. A mixed old/new pair
will cause the post-ingest hook to stop with `STALE phase=TRUST` after
a successful content receipt; do not retry the ingest, rollback, toggle
the marker or automatically repair files.

Before any future LIVE action, revalidate exact host/main, installed Git blobs,
the enabled marker, writable catalog/sitemap actors, active timer/service
state, shared advisory lock and staged-file absence. The publisher upgrade
is a **non-transactional two-file** swap; independent writer quiescence must
cover its entire mutation window. A separate, independently reviewed
installed Drive-ingester upgrade method/authorization must be identified
and approved: do **not** use the historical first-install-only installer or
an unreviewed direct overwrite. No new source change authorizes a host
mutation or standing future `PUBLISH` operation.

Preserve the immutable historical
`ops/contracts/ausmalwiese-sitemap-cutover-v1.json` record; its older
`candidate_release.drive_ingest_git_blob` still describes that earlier
cutover, not the new current source. Focused CI tests bind the current
ingester source to the reviewed publisher/generator bytes and reject
predecessor/mixed installed pairs before subprocess execution.

Google sitemap documentation:
https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap .
The shared lock is advisory; Python flock documentation:
https://docs.python.org/3/library/fcntl.html .

---

## Source-only coordinated triple upgrade: issue #1460

**Current owner-visible status:** source-only preparation, no host authority. The
reviewed successor to the **two-file** upgrade is a separate fixed-path
`scripts/upgrade-coloring-pages-sitemap-suite-v1.py`. The historical
`scripts/upgrade-coloring-pages-sitemap-publisher-v1.py` is **unchanged**.
Do not use the historical two-file procedure for this enabled-marker rollout.

### Exact release, targets and immutable candidates

| Installed target | Required OLD Git blob | Pinned NEW Git blob | Mode |
| --- | --- | --- | --- |
| `/usr/local/share/coloring-pages/coloring-pages-sitemap` | `5d1d37c32573aa8ac0d91f45b73938638fd183e9` | `f4ffaa4293f9c46f475f96d4409f05ff347a7590` | root:root 0444 |
| `/usr/local/bin/coloring-pages-sitemap-publish` | `4ade38f1225f4c1bc102fda8d5538f9262695d43` | `3263845045f6d38f31ff359158be90ab59006240` | root:root 0755 |
| `/usr/local/bin/coloring-pages-drive-ingest` | `b10dc43bceb8ac3b77d8af47661b11a4ca50ea90` | `c4e2f67e0154f705e2d46db9dcc87e6a69b108fd` | root:root 0755 |

The exact tracked `RPi5_main/main` SHA, clean checkout and script's own
tracked Git blob are checked through fixed-path, privilege-separated
`runuser`/Git before reading any candidates. No remote fetch, checkout
update, arbitrary source root or URL can be supplied. The root-only CLI
requires a separately reviewed exact `--expected-rpi5-main-sha` and
`--expected-marker-state=enabled|absent`, and **only** `--check` or
`--apply`. Marker bytes, root ownership, regular file type, modes and
shared existing Drive-ingest advisory lock inode are checked without
replacing the marker.

**Mandatory quiescence:** `--check` and `--apply` both check, via fixed
read-only `systemctl show`, that
`coloring-pages-admin-publish.service` and
`coloring-pages-publish-request-bridge.service` are *loaded, inactive and
have no pending job*. The last read-only host observation saw the ADMIN
service **active**, so execution must **STOP** until a separate exact
owner authorization safely controls that entrypoint. The tool does **not**
stop/start/restart/disable any service or timer. These two systemd guards
plus the existing `flock` are **necessary, not sufficient** to prove no
unreviewed direct Docker importer, remote executor or manual catalogue
writer. Independent approved writer quiescence must cover the entire
upgrade window, including resumption policy; an on-demand future writer
cannot be blocked by advisory locks alone.

After successful frozen preflight, all three successor files are staged with
exclusive no-follow creation into their destination directories, verified
and fsynced **before the first replacement**. The only replacement order is
**generator → sitemap publisher → Drive ingester**, each individually
`os.replace`d, directory-fsynced and hash-verified. The three replacements
are **not atomic as a group**. Quiescence and marker identity are
rechecked before each replacement. A failure after any staged-file
creation consumes that exact LIVE grant, preserves all remaining stage/mixed
state for diagnosis, and **STOPs** — no retry, rollback, removal or cleanup,
even if a service remains stopped. The CLI never publishes `sitemap.xml`,
imports content or calls another installer.

### Future owner decisions — not granted by source merge

1. Review and authorize an exact maintenance window and current writer
   quiescence protocol, including any permitted ADMIN/service/timer lifecycle
   mutations and recovery consequences. **Do not infer a stop/restart right
   from the upgrade command.**
2. After fresh exact installed OLD SHA/marker/lock/stage/service evidence,
   issue a **separate** owner Composite LIVE grant for **one** root-run of
   this exact script with a frozen checkout SHA, fixed paths, both marker
   and writer-quiescence guards and no retry. Technical `--check` alone
   never authorizes `--apply`.
3. Independently authorize any required restoration of previously stopped
   services. Keep the producer contract stable and disallow new ingests in
   the mixed-version interval. Existing post-publish marker `enabled`
   does not itself authorize content ingestion or new sitemap writes.
4. Publish the ten-static-URL `sitemap.xml` in another exact owner-gated,
   catalogue-SHA-256/prior-sitemap-SHA-256 bound one-shot operation;
   verify identical local/public XML separately. No Search Console action
   is implied.

The operator remains source-only until all gates are met. These safeguards
are documented by the official manuals:
- https://man7.org/linux/man-pages/man2/flock.2.html
- https://docs.python.org/3/library/os.html#os.replace
- https://man7.org/linux/man-pages/man1/systemctl.1.html
