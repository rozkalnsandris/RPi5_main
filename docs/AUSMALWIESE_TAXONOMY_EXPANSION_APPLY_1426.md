# Ausmalwiese taxonomy expansion apply — issue #1426

## Purpose

This source-only operator turns one owner-reviewed managed Topic expansion manifest into a bounded plan or one guarded runtime operation. It exists so #1395 does not need a long sequence of independent ADMIN Topic/link POST mutations.

The operator does not approve taxonomy. Candidate IDs from #1395 remain proposals until the owner separately approves exact Topic objects and exact Category↔Topic links.

## Fixed runtime contract

Operator: scripts/ausmalwiese_taxonomy_expansion_apply_v1.py

Fixed paths:

- Categories, read-only: /srv/coloring-pages-content/public/categories.json
- Topics: /srv/coloring-pages-content/public/topics.json
- Category↔Topic links: /srv/coloring-pages-content/state/admin-publish/category-topic-links.json
- Approved manifest: /srv/coloring-pages-content/state/admin-publish/taxonomy-expansion-approved-v1.json
- Shared lock: /srv/coloring-pages-content/state/drive-ingest/.lock
- Publication jobs: /srv/coloring-pages-content/state/admin-publish/jobs

No caller-selected runtime path is accepted.

## Approved manifest schema

Schema: ausmalwiese.taxonomy-expansion-apply.v1

Exact top-level keys are schema, mode, hashes, revisions, topics, links, and manifest_sha256. Mode must be APPROVED_APPLY. Hashes bind the current Category, Topic and link SHA-256 values; revisions bind their exact current revisions. The deterministic digest is SHA-256 over canonical JSON of every manifest key except manifest_sha256, using UTF-8, sorted keys and compact separators.

Each Topic object must satisfy the existing managed Topics v2 contract. Seasonal Topics require active_from and active_to; evergreen Topics do not. Each new Topic must be absent from the current registry and must receive at least one new link. Links may reference only existing Categories and the Topics newly introduced by the same manifest. Existing Topics/links cannot be rewritten through this operator.

Compatibility remains identical to the ADMIN publisher: seasonal Topics link only to jahreszeiten; evergreen Topics link only to non-jahreszeiten Categories.

## Plan

Plan mode is read-only. It requires:

    python3 scripts/ausmalwiese_taxonomy_expansion_apply_v1.py \
      --expected-source-sha <exact-main-sha> \
      --expected-manifest-sha256 <exact-manifest-digest> \
      --plan

It returns only bounded metadata: Topic IDs, Category/Topic pairs, counts, current/resulting hashes and current/resulting revisions. It does not write Topics, links, Categories, catalog, archive, media or job state.

Plan fails closed on source drift, manifest digest mismatch, stale hash/revision bindings, duplicate/unknown IDs, invalid Topic fields, incompatible Category↔Topic kind, noncanonical registry serialization or unsafe files.

## Apply boundary

Apply requires a separate exact LIVE owner authorization and the confirmation literal OWNER-AUTHORIZED-AUSMALWIESE-TAXONOMY-EXPANSION-APPLY.

Before the first mutation, the operator:

1. verifies exact clean RPi5_main/main source identity and origin;
2. obtains the existing shared publication lock without waiting;
3. rejects queued/running publication jobs;
4. rejects interrupted ADMIN/operator staging;
5. re-reads Categories, Topics, links and manifest under the lock;
6. revalidates exact hashes/revisions and deterministic manifest digest;
7. builds and validates both complete resulting registries;
8. verifies Topics mode 0644, links mode 0600, regular-file identity, ownership and no symlink/hardlink drift.

Zero-change manifests return UNCHANGED without mutation.

For a real change, both complete target files are computed before mutation. The operator then stages the Topics file in its own directory and the links file in its own directory, fsyncs each staged file, performs one atomic replacement per fixed target, fsyncs both directories and re-reads both results.

Topics and links are separate files in different directories, so Linux does not provide one cross-directory ACID rename for the pair. This operator therefore provides one prevalidated, lock-held, pre-staged two-file transaction, with each target replacement individually atomic. If any uncertainty or error occurs after the first staging mutation, the required behavior is STOP with evidence: no retry, rollback, cleanup or fallback ADMIN POST loop. Any orphan stage or partial state blocks later runs for manual review.

## Preservation rules

The operation:

- preserves every existing Topic object unchanged and in the same relative order;
- appends only the exact approved new Topic objects;
- preserves every existing Category↔Topic pair;
- adds only the exact approved new pairs and serializes the complete links set in canonical sorted order;
- increments Topic revision once when Topics change;
- increments links revision once when links change;
- never creates/renames/deletes a Category;
- never changes catalog memberships, archive, media, publication jobs, service state, secrets, permissions or external systems.

## Workflow after source merge

1. #1395 produces the exact owner-reviewed Topic/link proposal.
2. A separately authorized LIVE step materializes the exact approved fixed-path manifest and runs plan mode.
3. The owner reviews the exact plan/digest.
4. A fresh exact LIVE authorization may run apply mode.
5. Re-run the protected #1395 477-ID review/export against the expanded taxonomy.
6. Convert the complete review to the #1396 catalog classification apply manifest.
7. #1396 remains a separate owner-gated catalog mutation.

Issue #1426 grants source work only. Merge and every runtime write remain separately controlled by project policy.
