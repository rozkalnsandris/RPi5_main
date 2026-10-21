# Ausmalwiese catalogue hide playbook

Purpose: make future removal of wrongly published Ausmalwiese activities predictable and safe.

This playbook is for **unlisting** catalogue entries. It is not media deletion. GitHub is canonical for reviewed operator source and policy; the RPi5 LIVE files are canonical for the currently published catalogue and sitemap state.

## Scope and hard boundaries

A normal hide may change only the exact approved catalogue record(s), and only the sitemap when the current state and reviewed operator require it.

Do not delete or overwrite:

- `media/` files;
- originals;
- Drive files;
- inbox/receipts;
- analytics or engagement data.

Merge never grants LIVE authority. A LIVE apply requires a fresh owner authorization bound to the exact host, IDs and current baseline hashes.

After the first LIVE mutation, any error or ambiguity is **STOP**. No retry, rollback, cleanup or alternate mutation path without fresh owner authority.

## Fast path

### 1. Freeze exact targets

From the current LIVE `catalog.json`, record for every target:

- ID;
- exact title;
- exact category.

Do not rely only on chat history, filenames or screenshots.

If an image/library check is relevant, use it to identify the intended activity, but the LIVE catalogue record is the final target binding.

### 2. Read current LIVE state before choosing an operator

Read-only evidence must include:

- `catalog.json` SHA-256;
- `sitemap.xml` SHA-256;
- catalogue entry count;
- sitemap URL/detail count;
- whether every target exists in the catalogue;
- whether every target URL exists in the sitemap.

Also classify sitemap consistency instead of assuming catalogue and sitemap are 1:1.

### 3. Choose the correct state model

#### A. Catalogue and sitemap are aligned

Use an exact target-bound operator that removes:

1. the approved catalogue record(s);
2. the matching sitemap detail URL(s).

The operator must validate the full pre-state and produce candidate hashes in read-only `--check` mode before any apply.

#### B. Sitemap is already stale, but safely a subset of the catalogue

A **catalog-only** hide is acceptable only when all of these are true:

- the sitemap static route prefix is exactly the currently reviewed set;
- all sitemap detail IDs are valid, unique and sorted;
- every sitemap detail ID is present in the catalogue;
- target IDs are already absent from the sitemap;
- removing the target catalogue records still leaves every sitemap detail ID present in the post-hide catalogue.

In this case the reviewed operator must leave `sitemap.xml` byte-identical and mutate only `catalog.json`.

#### C. Any other mismatch

STOP and diagnose. Do not force the hide.

Examples:

- sitemap contains a detail ID absent from the catalogue;
- unsupported or unexpected sitemap routes;
- duplicate or unsorted detail IDs;
- target title/category changed;
- target unexpectedly absent from catalogue;
- baseline hashes drifted.

## 4. Always run read-only `--check` first

Required PASS evidence:

- exact target IDs;
- current catalogue SHA-256;
- current sitemap SHA-256;
- expected next catalogue SHA-256;
- expected next sitemap SHA-256;
- entry count before/after;
- `mutation_started: false`.

Do not use `--apply` if the check does not pass exactly.

## 5. Owner LIVE gate

The apply authorization should bind at minimum:

- host `rpi5`;
- exact target IDs;
- exact current catalogue SHA-256;
- exact current sitemap SHA-256;
- expected next catalogue SHA-256;
- whether sitemap mutation is allowed.

Do not widen the authorization to media deletion, Drive writes or unrelated LIVE work.

## 6. One apply only

Run the installed, reviewed operator exactly once with the frozen baseline hashes.

If it reports a failure after mutation begins, preserve evidence and STOP. Do not retry.

## 7. Post-verify

Read-only verification should prove:

- final catalogue SHA-256 equals the expected candidate;
- final sitemap SHA-256 equals the expected candidate/unchanged value;
- expected catalogue entry count;
- every target ID is absent from the catalogue;
- local HTTP serves byte-identical `catalog.json` and `sitemap.xml`.

Public read-only verification may then confirm that the removed activities are no longer listed.

## Important lesson from the N-R removal on 2026-10-21

The first N-R operator failed safely because it assumed sitemap URLs were exactly:

- home;
- `/kita`;
- every catalogue detail URL.

The actual sitemap also contained six category routes and was already missing multiple catalogue detail URLs. All N-R target URLs were already absent from the sitemap.

The correct path was therefore a reviewed **stale-sitemap catalog-only operator**. It removed exactly five catalogue records and left the sitemap unchanged.

Relevant reviewed precedent:

- `ops/bin/ausmalwiese-catalog-hide-alphabet-nr-20261021` — strict catalogue+sitemap path;
- `ops/bin/ausmalwiese-catalog-hide-alphabet-nr-stale-sitemap-20261021` — catalog-only stale-sitemap path;
- `docs/AUSMALWIESE_CATALOG_HIDE_ALPHABET_NR_20261021.md`;
- `docs/AUSMALWIESE_CATALOG_HIDE_ALPHABET_NR_STALE_SITEMAP_20261021.md`.

These operators are **target-bound examples**, not generic tools for future IDs. For a new activity set, first inspect current LIVE state and use or create a reviewed operator whose exact target and state contract matches that state.

## Short decision rule

`targets in catalog?` → no: STOP.

`targets in sitemap?` → yes: use reviewed catalogue+sitemap hide path.

`targets absent from sitemap, and sitemap detail IDs are a clean subset of catalog?` → yes: use reviewed catalog-only stale-sitemap path.

Anything else → STOP and diagnose before mutation.
