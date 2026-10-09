# Coloring Pages trusted sitemap publisher — source-only v1

Issue: #938. Source owner: \`RPi5_main\`. Consumer handoff:
\`coloring-pages@0aa691efaec880e7125b10ba3fb7b4e0996ca1c4\`,
\`docs/SITEMAP_PUBLISHER_HANDOFF_V1.md\`.

## What this delivers
A **host-owned, fixed-path** one-shot Python publisher
\`ops/bin/coloring-pages-sitemap-publish\` and a vendored byte-identical,
read-only \`ops/vendor/coloring-pages-sitemap\`. Vendor identity is the exact
upstream Git blob SHA-1 \`5644c8fd366c0c57f6339fddd163c5091ea134c5\`.
The operator verifies this pin before generating content.

Intended (not automatically installed) identities:
- operator: \`/usr/local/bin/coloring-pages-sitemap-publish\`, \`root:root\`, mode \`0755\`;
- generator: \`/usr/local/share/coloring-pages/coloring-pages-sitemap\`,
  \`root:root\`, mode \`0444\`;
- execution: \`andris\`, **never root**;
- content catalogue: \`/srv/coloring-pages-content/public/catalog.json\`;
- sitemap: \`/srv/coloring-pages-content/public/sitemap.xml\`;
- exactly the existing \`state/drive-ingest/.lock\` advisory lock.

No installation, content write, cron/timer, Docker restart or external
configuration mutation follows this source merge. The operator is not
executable on LIVE until reviewed, exact owner authorization separately
permits installation of these fixed files. Installation and first sitemap
publication are **distinct** LIVE decisions. Do not execute source checkout
code on the production host as a substitute for the fixed installed identity.

## CLI contract
- \`--check\` is read-only, returns a current catalogue digest, candidate
  sitemap digest, existing sitemap state, and URL count.
- \`--apply --expected-catalog-sha256=<exact> --expected-current-sitemap-sha256=<absent|exact>\`
  is a **single owner-gated operation**. The expected catalogue hash must
  match current raw bytes; the prior sitemap must match either \`absent\`
  or its full exact hash. Only host-owned fixed filesystem paths are allowed.
  No arbitrary path, shell, URL, network or other target is a CLI parameter.

The publisher requires fixed parent/lock/file metadata, locks the same
ingest inode with nonblocking exclusive \`flock\`, runs the pinned generator,
validates the full expected ordered URL set, stages exact XML via \`O_EXCL\`
inside the destination directory, verifies it byte-for-byte using the
upstream \`--verify-sitemap\` mode, checks catalogue and prior sitemap identity
again under the lock, then applies \`os.replace\`, \`fsync\` and checks local
origin \`127.0.0.1:9191/sitemap.xml\` returns identical XML with HTTP 200.
It does **not** submit to Search Console.

## Fail-closed and next gate
- \`flock\` is **advisory**. The operator can exclude the reviewed Drive
  ingester (which holds the same lock), but it cannot exclude an unreviewed
  direct Docker importer or other catalogue writer which ignores the lock.
  Before LIVE publication, independently verify no such writer is active or
  authorized; otherwise STOP. The code also detects catalogue identity
  drift immediately before replacement.
- Creating \`.sitemap.xml.publish.partial\` is the **first production mutation**.
  Any failure thereafter leaves state as-is; never retry, roll back,
  unlink/clean up the stage or restart outside a new exact owner gate.
- Caller must bind one frozen \`main\` SHA, installed binary fingerprints,
  current catalogue SHA, expected prior sitemap state, target, and
  one-time publication boundary before performing LIVE writes.
- After a successful one-shot publish, future content ingests do **not**
  automatically regenerate the sitemap. A separate reviewed freshness/
  scheduling contract would be needed.

Official references:
- https://man7.org/linux/man-pages/man2/flock.2.html
- https://docs.python.org/3/library/os.html#os.replace
- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
