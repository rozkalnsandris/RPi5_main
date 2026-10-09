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

## First-install-only source path (issue #940)

The separate GitHub-only implementation supplies
`scripts/install-coloring-pages-sitemap-publisher-v1.py` and isolated tests.
Installation requires a **separate exact owner LIVE authorization**, not this
source merge. The installer runs as root only after independent verification of
its reviewed source blob and exact `RPi5_main` revision. It exposes two
non-interchangeable modes:

- `--check --expected-rpi5-main-sha <full-sha>`: read-only preflight;
  validates local checkout on `main`, clean worktree, both reviewed Git blobs,
  fixed source/destination identities and **absent** installation targets.
  No directory or file creation occurs.
- `--apply --expected-rpi5-main-sha <full-sha>`: after fresh identical
  preflight, creates only the missing root-owned directory
  `/usr/local/share/coloring-pages` (0755), then the vendored generator
  `/usr/local/share/coloring-pages/coloring-pages-sitemap`
  (`root:root`, 0444), and finally the operator
  `/usr/local/bin/coloring-pages-sitemap-publish`
  (`root:root`, 0755). All new files use no-follow exclusive creation and
  exact byte/owner/mode verification. Directory and files are fsynced.

Both target files **and** the vendor directory must be absent. Any preexisting
file, directory or symlink is an error: **no overwrite, repin, upgrade,
permission repair, cleanup, rollback, service restart or fallback install
path** is allowed. Directory creation is the first authorized LIVE mutation.
An error afterwards leaves any partial installation as-is and stops.
The CLI does not accept arbitrary source roots, destination paths, or commands.

The reviewed source blobs must remain exactly:
- operator: Git blob SHA-1 `0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8`;
- generator: Git blob SHA-1 `5644c8fd366c0c57f6339fddd163c5091ea134c5`.

The local fixed owner-home `RPi5_main` checkout is a technical prerequisite,
not source of truth. A read-only checkpoint on 2026-10-09 showed its HEAD was
still `079bdcb8cfddf2261323d7a2074fa0a58629d94e`, behind the merged
operator source. The installer deliberately **does not** fetch, merge, or
update that checkout. Any source alignment must be separately trusted and
owner-authorized. A source checkout mismatch is a STOP before installation.

**First sitemap publication is a different owner gate**. The installer does
not call the publisher, inspect/write production catalogue data, change Drive,
Docker/systemd, service state, Cloudflare or Search Console, and does not
schedule future catalog refreshes.

Installer design reference: GNU Coreutils `install` identity/mode semantics
https://www.gnu.org/software/coreutils/manual/html_node/install-invocation.html
and Python `os.open` exclusive/no-follow flags
https://docs.python.org/3/library/os.html#os.open.



## Post-PUBLISH freshness — source-only issue #942

**One trigger, no timer:** in \`ops/bin/coloring-pages-drive-ingest\`, immediately after
a **new** full content import, independent HTTP verification and durable PASS receipt,
the shared \`state/drive-ingest/.lock\` context ends. Only then can the bounded
\`refresh_sitemap_after_new_ingest()\` hook run. \`ALREADY_PROCESSED\` returns
inside the lock and never refreshes a sitemap. The existing Drive/importer lock
is unchanged. No new scheduler, cron, systemd timer, Docker deployment, upstream
generator repin or Search Console call exists.

**Disabled by default, even after source merge:** hook executes only when an
independently owner-authorized, root-owned \`0444\` regular activation marker
\`/usr/local/share/coloring-pages/post-publish-v1.enabled\` exists with exact bytes
\`coloring-pages-sitemap-post-publish-v1\n\`. The marker and its parents must
have reviewed root ownership, with directories \`0755\`; symlinks and drift
STOP before any invocation. Ordinary image \`PUBLISH\` does not create the
marker and does not grant persistent sitemap writes. The merged source does not
install a new Drive ingester or create any marker. Before activation the default
behaviour of the installed operator stays unchanged.

With a valid marker, the hook verifies the **installed fixed-path** operator
\`/usr/local/bin/coloring-pages-sitemap-publish\` root:root \`0755\`, exact blob
\`0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8\`, and its pinned generator
root:root \`0444\`, blob
\`5644c8fd366c0c57f6339fddd163c5091ea134c5\`. Only its fixed CLI
\`--check\` is called first. If desired and existing sitemap SHA-256 agree,
the hook exits \`CURRENT\` without mutation; otherwise it calls one \`--apply\`
using only raw-byte catalog and previous sitemap fingerprints from the
validated check response. The underlying publisher reacquires the same advisory
lock, checks the exact current catalog and old sitemap, verifies the XML,
uses an exclusive stage and one atomic replacement, and verifies HTTP.
Race, advisory lock contention, unsafe metadata, stale hash or failure blocks
the refresh; **no retry, cleanup, rollback, repeat importer or alternative path.**

**Separate outcomes:** the already committed ingest receipt remains \`PASS\`,
and the operator retains its successful ingest exit status; it then prints exactly
one sanitized \`COLORING_PAGES_SITEMAP=DISABLED|CURRENT|REFRESHED|STALE\` line.
A \`STALE\` line also includes \`phase=GATE|TRUST|CHECK|APPLY\` and
\`recovery=EXPLICIT_OWNER_LIVE_GATE\`. Do not classify a stale sitemap as an
ingest failure, retry publication, remove a partial stage or rerun content ingest.
This line is an operational signal, **not** a separate persisted sitemap receipt.
A downstream PUBLISH UI must distinguish this line from the content receipt.

**Strict future activation (NOT authorized by issue #942 or its merge):**
1. Independently prove the only enabled catalogue writers cooperate with the
   existing ingest lock, or obtain a different reviewed quiescence gate.
   \`flock\` is advisory and cannot exclude an out-of-band writer.
2. Read-only preflight: refresh exact \`RPi5_main/main\`, image/ingester source
   and installed identities, parent modes, active lock/writers, current catalogue
   raw hash, existing sitemap hash, \`--check\` result and local HTTP equality.
   Verify marker **absent**, unless a separately authorized activation
   explicitly covers known previous state. Never silently repair permissions.
3. Seek one exact owner **LIVE** authorization for the fixed new installed
   Drive-ingest operator update AND first creation of this exact marker
   (or separately authorized bounded gates). Include exact source blobs,
   host target, immutable expected baseline, writer exclusion, allowed
   mutation sequence and error semantics. Merging the source and content
   \`PUBLISH\` permission are not that authorization.
4. After authorized activation, verify the installed binary and root gate,
   run one *genuine* owner-approved new ingest through the reviewed path,
   verify the distinct ingest and sitemap statuses, identical HTTP XML and
   URL set, and preserve sanitized proof. Do not create test content in LIVE.
5. On failure after the first authorized mutation, STOP and preserve evidence;
   no automatic retry, removal of marker, rollback or cleanup. **Disabling**
   the marker is a new host filesystem mutation needing another exact owner
   authorization; fail-closed source-only diagnostics cannot disable it.

This is not a permanent owner blanket approval for all future sitemap
mutations until a separately reviewed LIVE standing authorization explicitly
defines that scope. Until then the hook must remain disabled. Source-only
tests: \`tests/test-coloring-pages-sitemap-post-publish-v1.py\`.
