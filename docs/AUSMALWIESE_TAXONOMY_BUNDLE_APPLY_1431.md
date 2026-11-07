# Ausmalwiese taxonomy bundle apply — issue #1431

## Purpose

This extends the merged #1426 operator so one owner-reviewed manifest can describe a bounded taxonomy bundle across all three managed registries:

- Categories;
- Topics;
- Category↔Topic links.

It exists specifically to support the exact owner-approved #1395 taxonomy decision without a chain of independent ADMIN POST mutations.

## Fixed runtime contract

Operator: `scripts/ausmalwiese_taxonomy_expansion_apply_v1.py`

Fixed paths:

- Categories: `/srv/coloring-pages-content/public/categories.json`
- Topics: `/srv/coloring-pages-content/public/topics.json`
- Category↔Topic links: `/srv/coloring-pages-content/state/admin-publish/category-topic-links.json`
- Approved manifest: `/srv/coloring-pages-content/state/admin-publish/taxonomy-expansion-approved-v1.json`
- Shared lock: `/srv/coloring-pages-content/state/drive-ingest/.lock`
- Publication jobs: `/srv/coloring-pages-content/state/admin-publish/jobs`

No caller-selected runtime path is accepted.

## Manifest v2

Schema: `ausmalwiese.taxonomy-expansion-apply.v2`

Exact top-level keys:

- `schema`
- `mode` = `APPROVED_APPLY`
- `hashes`
- `revisions`
- `categories`
- `topics`
- `links`
- `manifest_sha256`

`hashes` binds the exact current Category, Topic and link SHA-256 values. `revisions` binds all three exact current revisions. The manifest digest is deterministic canonical JSON over all keys except `manifest_sha256`.

Category additions are bounded and must be new stable IDs with normalized non-empty labels. Topic additions retain the managed Topics v2 object contract. New links may connect:

- a new Topic to an existing or new compatible Category;
- an existing Topic to a new compatible Category.

A link between two already-existing registry objects is rejected by this operator. Existing Category, Topic and link rows cannot be edited, renamed or deleted.

Every newly added Topic must have at least one link. Every newly added Category must have at least one link.

Seasonal compatibility remains unchanged: seasonal Topics link only to `jahreszeiten`; evergreen Topics link only to non-`jahreszeiten` Categories.

## Read-only plan

```text
python3 scripts/ausmalwiese_taxonomy_expansion_apply_v1.py \
  --expected-source-sha <exact-main-sha> \
  --expected-manifest-sha256 <exact-manifest-digest> \
  --plan
```

Plan mode returns only bounded metadata:

- Category IDs to add;
- Topic IDs to add;
- Category↔Topic pairs to add;
- addition counts;
- before/after SHA-256 for Categories, Topics and links;
- before/after revision for Categories, Topics and links;
- manifest digest.

Plan mode never writes.

## Apply boundary

Apply remains separately owner-gated and requires the exact confirmation literal already defined by the operator.

Before first mutation the operator:

1. verifies exact clean `RPi5_main/main` source identity and origin;
2. takes the shared publication lock without waiting;
3. rejects active publication jobs;
4. rejects interrupted ADMIN or taxonomy staging for any of the three registries;
5. re-reads Categories, Topics, links and the approved manifest under lock;
6. revalidates exact source hashes, revisions and deterministic digest;
7. computes all three complete resulting registry documents;
8. validates all three candidates against the resulting Category/Topic universe;
9. verifies fixed-target regular-file identity, ownership and modes.

Zero-change manifests return `UNCHANGED` without mutation.

For a real change, all three complete target documents are computed and validated before the first mutation. Then all three same-directory temporary files are staged and fsynced before fixed-target replacement. Categories and Topics use mode `0644`; private links use `0600`.

The three registries are separate files and there is no cross-file ACID rename. This is therefore a lock-held, prevalidated, pre-staged multi-file transaction in which each target replacement is individually atomic. After the first staging mutation, any failure or uncertainty requires terminal STOP with evidence. No retry, rollback, cleanup or alternate ADMIN POST loop is permitted automatically.

## Preservation

The operator preserves every existing Category and Topic object in original relative order. New Category/Topic objects are appended exactly as approved. Existing Category↔Topic pairs are preserved and the complete resulting pair set is canonical sorted.

Only registries that change increment their revision once. No catalog memberships, IDs, titles, media, archive entries, publication jobs, service state, secrets, settings or permissions are changed.

## Exact #1395 approved bundle

The owner-approved decision is recorded in #1395 proposal comment `6712760996` and approval receipt `6712767989`. This source issue does not materialize or apply that runtime manifest; it only makes the exact approved shape safely representable.

## Workflow after merge

1. Freshly verify installed/runtime source plus current Category/Topic/link hashes and revisions.
2. Materialize the exact owner-approved v2 manifest under a separate LIVE authorization.
3. Run read-only plan and review its exact digest/resulting hashes.
4. Run apply only under a new explicit LIVE authorization.
5. Re-run the protected #1395 477-ID human review/export against the expanded taxonomy.
6. Convert the completed review to the separately gated #1396 catalog apply manifest.

Issue #1431 is source-only. Merge and all runtime writes remain separate owner gates.
