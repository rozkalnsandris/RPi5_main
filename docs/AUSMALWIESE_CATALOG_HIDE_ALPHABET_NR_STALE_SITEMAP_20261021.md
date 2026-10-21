# Ausmalwiese N–R catalog-only hide with stale sitemap

Issue: #1146. Source-only corrective path.

## Exact targets

- `5008429` — `N - Nashorn und Nuss` — `alphabet`
- `3559941` — `O - Orange und Ofen` — `alphabet`
- `3255194` — `P - Pinguin und Pilz` — `alphabet`
- `0363214` — `Q - Qualle und Quadrat` — `alphabet`
- `7403304` — `R - Raupe und Regenbogen` — `alphabet`

Observed LIVE baseline that motivated this source:
- catalog SHA-256 `ea7f292c9f5df807881e5116313b5c1a9aed6fac06b16827aac4958cffb11a69`;
- sitemap SHA-256 `e5a6b0c060985020711357cc45b354f296282da2a51117e806001802936a9df3`;
- catalog has 368 IDs;
- sitemap has 335 detail IDs plus home, `/kita` and the six current category routes;
- sitemap detail IDs are a strict subset of catalog IDs;
- all five target IDs are already absent from sitemap.

## Source contract

Operator:
`ops/bin/ausmalwiese-catalog-hide-alphabet-nr-stale-sitemap-20261021`

First-install-only installer:
`scripts/install-ausmalwiese-catalog-hide-alphabet-nr-stale-sitemap-20261021.py`

The operator is intentionally catalog-only. It:
1. binds all five exact ID/title/category tuples;
2. validates the current sitemap static route prefix exactly: home, `/kita`,
   `/tiere`, `/fahrzeuge`, `/alphabet`, `/lernen`, `/figuren`,
   `/jahreszeiten`;
3. accepts a stale detail set only when every sitemap detail ID is valid,
   unique, sorted and already present in the current catalog;
4. requires all five target IDs to be absent from sitemap;
5. computes a catalog with exactly those five records removed while preserving
   all remaining order and fields;
6. requires both exact current catalog and sitemap SHA-256 values on
   `--apply`;
7. stages only the catalog candidate with `O_EXCL|O_NOFOLLOW`, fsyncs,
   rechecks both baselines under the existing Drive-ingest lock, atomically
   replaces only `catalog.json`, and leaves `sitemap.xml` byte-identical;
8. proves local HTTP returns the new catalog bytes and unchanged sitemap bytes.

The first production mutation is creation of
`.catalog.json.hide-alphabet-nr-stale-sitemap-20261021.partial`.

No media, originals, inbox, receipts, Drive files, analytics or engagement data
are deleted or overwritten. No sitemap regeneration is attempted by this
operator. The existing sitemap staleness is a separate follow-up concern.

Source merge grants no LIVE authority. Installation and final `--apply` are
separate owner-gated LIVE operations. After the first LIVE mutation, any error
is STOP with no retry, rollback, cleanup or alternate mutation path.
