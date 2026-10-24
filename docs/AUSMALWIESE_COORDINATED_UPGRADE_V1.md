# Ausmalwiese coordinated ingester + sitemap upgrade (SOURCE ONLY)

Owner scope: RPi5_main #996, dependency source merges PR #1027 and PR #1028.
The official host-side merged source is *not* proof of installed LIVE state.
This proposal covers the observed pre-cutover installed trio on RPi5:
- ingester Git blob `b1e796696307dcdbc9f92c1caf190c38032ccd71` (root:root, 0755)
- publisher `0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8` (root:root, 0755)
- generator `5644c8fd366c0c57f6339fddd163c5091ea134c5` (root:root, 0444)
- active post-PUBLISH marker `post-publish-v1.enabled` (root:root, 0444)
- trusted Drive ingest advisory lock `.lock` (andris:andris, 0600)

## Contract / no implicit LIVE authority

The source-only tool `scripts/upgrade-ausmalwiese-coordinated-v1.py`
pins three new Git blobs; `ops/bin/coloring-pages-drive-ingest` now
builds `PUBLIC_ORIGIN=https://ausmalwiese.de` with matching catalog/media
HTTP proofs, publisher pins and generator pins.

The **enabled Post-PUBLISH marker remains untouched**. It is unsafe to
change one component independently while the old ingest might invoke its
post-ingest hook outside the shared lock. Before either `--check` or
`--apply` succeeds, a separately owner-authorized root:root 0444 fixed
file `/usr/local/share/coloring-pages/sitemap-ingest-quiesced-v1.confirmed`
must exist with exact bytes `ausmalwiese-sitemap-ingest-quiesced-v1\n`.
The file is an attestation, **not proof in itself**: an independently
authorized human/operator must first verify all Drive, external automation,
importer, post-ingest and catalogue writers, including any in-flight process,
are stopped and cannot restart throughout the entire upgrade. Recheck before
any LIVE decision. Creating this file and stopping writers are **separate
LIVE mutations requiring explicit authority**. Do not create it under
a bare START, MERGE or this SOURCE grant.

The candidate operator accepts only `--check` or `--apply` and an exact
`--expected-rpi5-main-sha`. It executes root-only with a clean, exact
`RPi5_main/main` checkout. It verifies source blobs/modes, fixed own
source/parent helper, old installed root identities, enabled marker,
quiescence attestation, stage absence, and holds the original same-inode
non-blocking Drive ingester lock. It revalidates before its first mutation.

## Ordered operation / STOP

Staging: generator -> publisher -> ingester, each with O_EXCL/O_NOFOLLOW,
root ownership, mode, fsync, and exact byte verification. Replacements:
generator -> publisher -> ingester, each atomic per file with read-back.
**Three-file exchange is not a transaction**; no concurrent writer or
importer is safe during the intermediate mixed state. Check marker and
quiescence inode/bytes before each replacement and at end.

First stage creation consumes the future exact owner LIVE authorization.
Every error from that point is STOP with partial state retained, no
automatic retry, rollback, cleanup, alternative route, chmod, restart, or
overwrite recovery. A mixed or already upgraded state also fails closed.

## Later owner gates (not included)

1. Fresh exact RPi5 source/host identity and quiescence inspection.
2. Independently authorize source fast-forward of RPi5 checkout if needed.
3. Obtain a separately authorized, verified maintenance window and trusted
   quiescence file materialization; no changes to the active marker.
4. Obtain *another exact* LIVE upgrade gate bound to three old blob hashes,
   exact merged main SHA, target host and paths, lock, marker and quiescence state.
5. Independently coordinate coloring-pages PR #214 application deployment
   and QR Worker new-domain behavior; until verified, the new ingester's
   public HTTP checks may fail, so do not resume ingestion.
6. Authorize sitemap publication separately; validate all new-domain URLs,
   then last, authorize exact scoped legacy hostname 301 and verify single-hop
   path/query preservation. Search Console remains a separate owner action.

NO MERGE, LIVE, DNS, Cloudflare, secrets, permissions or sitemap content
mutation is authorized by this source-only PR.
