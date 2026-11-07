# Ausmalwiese catalog classification apply v1 — issue #1396

SOURCE ONLY. This change does not install, stage, read, or mutate the protected RPi5 catalog.

The operator is `scripts/ausmalwiese_catalog_classification_apply_v1.py`. It exists to apply one already human-reviewed Category/Topic manifest after #1395 is complete.

Runtime targets are fixed in source:

- catalog: `/srv/coloring-pages-content/public/catalog.json`
- categories: `/srv/coloring-pages-content/public/categories.json`
- topics: `/srv/coloring-pages-content/public/topics.json`
- Category↔Topic links: `/srv/coloring-pages-content/state/admin-publish/category-topic-links.json`
- approved manifest: `/srv/coloring-pages-content/state/admin-publish/classification-approved-v1.json`
- shared lock: `/srv/coloring-pages-content/state/drive-ingest/.lock`

The caller cannot select alternate paths.

## Manifest contract

The fixed schema is `ausmalwiese.catalog-classification-apply.v1`, derived from review schema `ausmalwiese.catalog-classification-review.v2`.

A valid manifest must contain:

- exact SHA-256 of catalog, Categories, Topics and Category↔Topic links;
- exact category/topic/link revisions;
- exactly one review decision for every current catalog ID, including legacy non-seven-digit IDs;
- only `approved`, `rejected` or `deferred` decisions — no `pending`;
- exact before/after ordered Categories and Topics;
- a bounded reason and confidence value;
- deterministic `manifest_sha256` over the complete manifest except that digest field.

Current catalog entries may have no Topic. An approved changed entry must have at least one valid Topic linked to one of its selected Categories. Rejected/deferred rows are preserved unchanged by the operator.

## Plan

`--plan` is read-only. It validates source identity, exact manifest digest, all current hashes/revisions, complete ID coverage and Category↔Topic compatibility, then reports:

- manifest SHA-256;
- catalog before/after SHA-256;
- changed/unchanged counts;
- exact changed IDs.

It does not write catalog, registry, jobs, media, archive or manifest state.

## Apply boundary

Future apply requires a separate fresh owner LIVE authorization binding:

- exact reviewed `RPi5_main` main SHA;
- exact manifest SHA-256 returned by plan;
- host `rpi5`;
- fixed operator and fixed catalog target;
- one catalog classification apply only.

The source confirmation literal is `OWNER-AUTHORIZED-AUSMALWIESE-CATALOG-CLASSIFICATION-APPLY`.

Apply acquires the existing publication/catalog lock, rejects queued/running publication jobs and interrupted catalog/taxonomy staging, then re-reads and revalidates the entire catalog/taxonomy/link/manifest state under lock. Zero-change plans do not mutate.

For a non-empty plan, the only production data change is one complete catalog replacement: write same-directory exclusive temporary file, fsync, `os.replace`, fsync directory, then exact post-read/hash verification. No per-ID POST loop is used.

After the first filesystem mutation, any error is terminal STOP. There is no retry, rollback, cleanup or fallback individual edit path.

The operator never changes titles, IDs, page order, media/original paths, age, difficulty, archive records, Categories, Topics or Category↔Topic registries.

## Source checks

```text
python3 scripts/ausmalwiese_catalog_classification_apply_v1.py --check-source
python3 tests/test-ausmalwiese-catalog-classification-apply-v1.py
```

Offline coverage includes legacy IDs, missing Topic before-state, full review coverage, stale taxonomy/hash rejection, invalid links, current-before mismatch, active-job blocking, zero-change behavior, one atomic catalog replacement, and preservation of unrelated catalog fields.

Merge does not authorize LIVE plan, manifest staging, apply, restart, installation or any registry/catalog mutation.
