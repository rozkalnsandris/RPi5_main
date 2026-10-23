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
