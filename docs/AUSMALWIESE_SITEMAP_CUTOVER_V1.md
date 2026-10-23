# Ausmalwiese sitemap source cutover — reviewed candidate

Status: **SOURCE ONLY**. Consumer dependency: `coloring-pages` PR #214 HEAD `af7ffbdcfb2ddad1247ee4b8ae681562fc1ede38`.
RPi5 issue: #996. This source PR does not approve a merge, host upgrade, sitemap publication,
Cloudflare Worker deployment or old-host redirect.

## Source alignment
- Vendor `ops/vendor/coloring-pages-sitemap` is byte-identical to consumer PR #214's
  `tools/coloring-pages-sitemap`, Git blob `49c8ba34cf0a4c4ab100463df9adacc4c6e90c2c`.
- Host publisher `ops/bin/coloring-pages-sitemap-publish` generates and validates
  `https://ausmalwiese.de/`, `/kita`, and exactly the catalogue-backed detail URLs.
  Candidate publisher Git blob: `7b0330f30e27d6fe9c5f3e4fbf81fc6473ade660`.
- First-install-only installer pins the candidate bytes, but **continues to reject
  existing target directories and files**. Never invoke its `--apply` for an upgrade.
- Post-ingest freshness hook's *source* expected operator+generator blobs are aligned
  to the same candidate. It stays gated by the separate root-owned marker, and the
  existing deployed binary is not silently changed by this source commit.

## Existing installation upgrade — deliberate HOLD
An existing `/usr/local/bin/coloring-pages-sitemap-publish` and
`/usr/local/share/coloring-pages/coloring-pages-sitemap` **cannot** be upgraded with
the first-install-only script. No reviewed upgrade executor is delivered here.
The fixed-path, exact-old-to-new upgrade requirements are frozen in
`ops/contracts/ausmalwiese-sitemap-cutover-v1.json`; a new, separately
source-reviewed upgrade executor and explicit owner LIVE authorization are
required before touching installed files. Old and new installed components may
not be swapped as an assumed atomic pair. Independently validate all old/current
blob identities and permissions, post-publish marker state, source checkout,
writer quiescence and shared lock before the first mutation. On an error after
the first mutation: STOP with state preserved; no retry/rollback/cleanup.

Any new installed post-ingest operator needs a separately authorized host
deployment too; its source pin change alone never replaces the installed version.
The Drive ingester's `PUBLIC_ORIGIN` is still the legacy hostname and must be
reconciled under an independently scoped source/runtime decision before retiring
the old hostname or relying on post-ingest public proofs.

## Ordered rollout / owner gates
1. Review source #214 and this PR; do **not** merge either merely because CI passes.
2. Separately review the trusted upgrade implementation/installed binary pins and
   coordinate with ingestion so no catalogue writer ignores the advisory lock.
3. Owner-approve the needed source merges and exact RPi5 upgrade(s), each with
   current SHA/binary/host baseline and fail-closed semantics.
4. Coordinate application deployment, QR Worker direct destination, updated
   host sitemap publication from a fresh live catalogue snapshot; verify that the
   public sitemap contains only `ausmalwiese.de` URLs and preserves every ID.
5. Only after public acceptance and stats/health verification, separately authorize
   the exact legacy `coloring.rozkalns.net` 301 rule. Search Console change of
   address remains a separate owner step.

Historic v1 hashes in `docs/COLORING_PAGES_SITEMAP_PUBLISHER_V1.md` describe
previously reviewed source/install contracts and must not be mistaken for the
candidate release above. No runtime state is inferred from GitHub source.
