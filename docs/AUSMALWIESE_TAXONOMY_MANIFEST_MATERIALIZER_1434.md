# Ausmalwiese approved taxonomy manifest materializer — issue #1434

## Purpose

This source path turns the exact owner-approved #1395 taxonomy decision into the fixed runtime manifest consumed by the #1431 taxonomy bundle operator. It removes the need to compose runtime JSON manually.

The approved source bundle is:

`ops/admin/coloring-pages/taxonomy-approved-1395-v1.json`

Its exact raw SHA-256 is:

`15eb5e004b82115d79d2bcb0f4e0fec838f6a62eeb086bae28aad3ca67bffea4`

Provenance is pinned to:

- #1395 proposal comment `6712760996`
- #1395 owner approval receipt `6712767989`

The materializer is:

`scripts/ausmalwiese_taxonomy_manifest_materialize_v1.py`

## Fixed targets

The materializer accepts no caller-selected runtime paths.

It reads:

- Categories: `/srv/coloring-pages-content/public/categories.json`
- Topics: `/srv/coloring-pages-content/public/topics.json`
- Category↔Topic links: `/srv/coloring-pages-content/state/admin-publish/category-topic-links.json`
- shared publication lock: `/srv/coloring-pages-content/state/drive-ingest/.lock`
- publication jobs: `/srv/coloring-pages-content/state/admin-publish/jobs`

It can write only:

`/srv/coloring-pages-content/state/admin-publish/taxonomy-expansion-approved-v1.json`

It never applies Category, Topic or link registries and never changes catalog metadata.

## Source bundle contract

Schema:

`ausmalwiese.taxonomy-approved-bundle.v1`

The source file contains exactly:

- Category `natur` — `Natur & Essen`;
- 12 approved Topic objects;
- 15 approved Category↔Topic links;
- the exact proposal and approval comment IDs.

The materializer validates the complete source file against its pinned raw SHA-256 before use. A source-data edit therefore requires an explicit reviewed code/data change, not an unnoticed runtime variation.

## Generated runtime manifest

The generated manifest uses the #1431 consumer schema:

`ausmalwiese.taxonomy-expansion-apply.v2`

The materializer reads the current three registry files, validates them with the same functions used by the #1431 consumer, computes their exact SHA-256/revisions, inserts the approved source bundle, computes the deterministic `manifest_sha256`, and passes the generated object back through the #1431 consumer validation and plan logic.

The manifest is therefore always bound to the exact current runtime taxonomy state.

## Read-only plan

```text
python3 scripts/ausmalwiese_taxonomy_manifest_materialize_v1.py \
  --expected-source-sha <exact-installed-main-sha> \
  --plan
```

`--emit-summary` is an equivalent read-only summary mode.

The bounded output includes:

- source bundle SHA;
- provenance comment IDs;
- generated manifest digest;
- Category IDs, Topic IDs and link pairs to add;
- before/after hashes and revisions for Categories, Topics and links.

It does not print full runtime registries and it performs no write.

For the sanitized baseline recorded when #1434 was opened:

- Category before: revision 1 / `fe76364e6245b772d21fb080d982dcbb90de420dd2f2a1056c7a1248d7cab635`
- Topic before: revision 1 / `a13d970821e96e86ae8a574417610ae2239178c363bbf83c014c7d8b61d1201a`
- links before: revision 2 / `7b6320b9ac46d33d28319648769f20bf0f59a11a64aaeadadf4007e8d6f3abc6`

the deterministic manifest digest is:

`6cb9bd42f89ba925239deccf9ce4cec164f386bdca78afe39d0d9942381e5bb6`

and the expected resulting registries are:

- Category revision 2 / `94d64efc25727ad4d3591be1586485709eca2b350ce5e7b1546d9aea11c0ae16`
- Topic revision 2 / `804869a4dc44c9761280dc3653524014dcabf74131cfa59805048a275fcf96c4`
- links revision 3 / `8c90863b9dbcd35a76b474712d76ebc50935805dbda785800a713a5496fe7289`

Those values are evidence, not permanent LIVE truth. Any later runtime drift produces a differently bound manifest or a validation STOP.

## Materialization boundary

Runtime materialization is not authorized by #1434 source work.

A future separately owner-authorized materialization uses the exact confirmation literal:

`OWNER-AUTHORIZED-AUSMALWIESE-TAXONOMY-MANIFEST-MATERIALIZE`

Before first mutation, the operator:

1. verifies exact clean installed `RPi5_main/main` source identity and origin;
2. obtains the shared publication lock without waiting;
3. rejects queued/running publication jobs;
4. rejects interrupted ADMIN, taxonomy apply or materializer staging;
5. validates current registry files and the immutable source bundle;
6. generates and consumer-validates the complete manifest;
7. verifies the fixed target parent and any existing manifest identity/mode/ownership.

If the target already contains byte-identical generated content, it returns `UNCHANGED` without mutation. Any different existing manifest is a STOP.

For an absent target, it writes one mode-`0600` same-directory temporary file, fsyncs it, performs one atomic replace, fsyncs the directory and re-reads the final exact bytes.

The first staged-file creation is the first filesystem mutation. Any error after that point is terminal STOP with evidence. There is no automatic retry, rollback, cleanup or alternate writer.

## Future workflow

1. Merge #1434 source only after explicit owner merge approval.
2. Freshly inspect RPi5 source/runtime state.
3. Under a separate exact LIVE authorization, sync the reviewed source if needed, materialize one exact manifest, and run the read-only plan.
4. Owner reviews the exact manifest digest and resulting registry hashes/revisions.
5. Under a new explicit LIVE authorization, run the #1431 registry apply.
6. Re-run the protected #1395 477-ID human review/export against the expanded taxonomy.
7. Feed that complete reviewed export to the separately gated #1396 catalog apply path.

No source merge grants runtime materialization or taxonomy apply authority.
