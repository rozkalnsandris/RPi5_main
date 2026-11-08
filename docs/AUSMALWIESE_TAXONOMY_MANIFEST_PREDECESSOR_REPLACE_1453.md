# Ausmalwiese #1437 taxonomy staging predecessor replacement

Issue: `#1453`

## Purpose

The #1437 taxonomy manifest materializer writes only the fixed staging target:

`/srv/coloring-pages-content/state/admin-publish/taxonomy-expansion-approved-v1.json`

The first LIVE preflight after #1440 merged found that this target still contains
the exact previously approved #1395 staging manifest. The taxonomy registries
have already advanced from the #1395 source revisions `1/1/2` to `2/2/3`,
so retaining the old staging file is expected historical state rather than a
new taxonomy input.

The #1437 materializer intentionally rejected arbitrary existing content. Issue
#1453 adds one narrow predecessor exception without adding a generic replace
mode.

## Exact replaceable predecessor

Replacement is permitted only when all normal target metadata checks pass and
the existing bytes have raw SHA-256:

`66282e777d0546b3d160135c225c6305e701a52894caaf88417bdc6c9335afac`

Those exact bytes must decode to:

- schema `ausmalwiese.taxonomy-expansion-apply.v2`;
- mode `APPROVED_APPLY`;
- logical manifest SHA-256
  `6cb9bd42f89ba925239deccf9ce4cec164f386bdca78afe39d0d9942381e5bb6`;
- Category source revision `1` and SHA-256
  `fe76364e6245b772d21fb080d982dcbb90de420dd2f2a1056c7a1248d7cab635`;
- Topic source revision `1` and SHA-256
  `a13d970821e96e86ae8a574417610ae2239178c363bbf83c014c7d8b61d1201a`;
- links source revision `2` and SHA-256
  `7b6320b9ac46d33d28319648769f20bf0f59a11a64aaeadadf4007e8d6f3abc6`.

The focused regression reconstructs that predecessor from the reviewed #1395
source fixtures and asserts both its raw and logical identities.

## Replacement semantics

The existing materializer states become:

- target absent: materialize the exact #1437 manifest;
- target already byte-identical to #1437: return `UNCHANGED`;
- target is the exact pinned predecessor above: perform the same single staged
  atomic replacement used for absent targets;
- any other existing target bytes, unsafe metadata or symlink: STOP.

All original gates remain mandatory: exact clean source SHA/origin, shared
publication lock, no queued/running publication job, no interrupted staging,
exact current taxonomy hashes/revisions, exact #1437 source manifest, target
parent ownership and target mode/ownership.

The first same-directory temporary-file creation remains the first filesystem
mutation. Any error after that point preserves evidence and STOPs. There is no
automatic retry, rollback, cleanup or alternate writer.

## Authority

This source change does not authorize runtime replacement. After merge and
fresh host revalidation, the predecessor replacement still requires a new exact
owner LIVE authorization. Taxonomy registry apply and catalog classification
apply remain separate later owner gates.
