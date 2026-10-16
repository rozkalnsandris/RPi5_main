# Ausmalwiese sitemap: exact old-to-new upgrade source

Source-only candidate. Depends on RPi5_main PR #1027 at 71640856c328fa68636041f9ec023a2cc20fe4da,
and coloring-pages PR #214. There is **no standing LIVE permission**.

The reviewed candidate in scripts/upgrade-coloring-pages-sitemap-publisher-v1.py
pins the installed old publisher Git blob 0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8
and old generator blob 5644c8fd366c0c57f6339fddd163c5091ea134c5.
Only exact new publisher 7b0330f30e27d6fe9c5f3e4fbf81fc6473ade660
and generator 49c8ba34cf0a4c4ab100463df9adacc4c6e90c2c are accepted.

## Before any future LIVE authorization
- Merge the dependency and this PR only with separate explicit owner MERGE
  approvals. Independently check exact new merged main SHA, clean main checkout,
  exact tracked candidate blobs and installed old root-owned bytes/modes.
- Establish host-local evidence that **all** catalogue writers are quiescent,
  none bypass the shared advisory lock, and the post-publish marker is absent.
  The tool's read-only --check alone cannot establish complete quiescence.
- Old installed operator must be root:root 0755, generator root:root 0444.
  A missing, mixed, already updated, symlinked, or tampered installation is a STOP.
- A fixed trusted source lookup uses unprivileged owner-run Git; do not use the
  first-install-only installer to replace any existing installation.
- Bind one new exact host LIVE decision to the frozen RPi5_main revision, exact
  installed baselines, current lock and marker states, target paths and no-retry
  semantics. Source merge does not authorize this.

## Operation contract (not execution authorization)
The only accepted source CLI modes are --check and --apply, both with
--expected-rpi5-main-sha. Root-only apply first holds the shared nonblocking
Drive ingester flock, rejects an enabled marker or pre-existing stages,
re-verifies trusted candidates under the lock, stages both exact replacement
files and fsyncs them, then atomically replaces **generator first** and
**publisher second**, verifying each replacement with mode/owner/blob checks.

**This is not a transactional two-file swap.** In the intermediate state the old
publisher rejects the new generator. All competing writers and new publication
operations must remain stopped until both replacements are verified.

The **first stage-file creation** is the first LIVE mutation. Any subsequent
error means STOP preserving state: no retry, rollback, cleanup, unlink,
permission repair, alternate mutation, or service restart. Partial state
requires a fresh owner risk decision. An already enabled post-ingest marker
is not silently disabled or ignored.

The installed Drive ingester's separate trust pins and PUBLIC_ORIGIN still
require separately scoped source and LIVE review; this upgrade does not alter
them. Further gates: PR #214 deployment, Cloudflare QR Worker deployment,
one owner-authorized LIVE sitemap publication with exact catalogue/prior
sitemap fingerprints, verified new-host sitemap/SEO, then narrowly scoped
legacy 301. Google Search Console Change of Address is a separate step.
