# Ausmalwiese public Category↔Topic projection — #1464

## Purpose

The canonical Category↔Topic association registry remains private at
`/srv/coloring-pages-content/state/admin-publish/category-topic-links.json`.
The public application receives only a deterministic projection at:

```text
/category-topics.json
```

The projection is not a second taxonomy source. It is valid only when its three
integrity bindings match the canonical public `categories.json`, public
`topics.json`, and private link registry.

## Public schema

Schema: `rozkalns.coloring-pages.category-topics.v1`.

Exact fields:

- `schema`
- `revision` — private Category↔Topic link revision
- `category_revision`
- `topic_revision`
- `category_sha256`
- `topic_sha256`
- `source_links_sha256`
- `links[]` with only `category` and `topic` stable IDs

No labels, icons, legacy search terms, ADMIN paths, host state, authentication
metadata, CSRF values, catalog entries, media paths, PII, credentials or secrets
are included.

Links are lexicographically ordered and unique. Every Category and Topic ID is
validated against the exact current registries, and seasonal Topics remain
compatible only with `jahreszeiten`.

## Consumer contract for `rozkalnsandris/coloring-pages#507`

The public app should fetch `categories.json`, `topics.json`, and
`category-topics.json` from the same `https://ausmalwiese.de` origin.

Before rendering Topic children under Categories it must verify:

1. `schema === "rozkalns.coloring-pages.category-topics.v1"`;
2. Category and Topic revisions match the fetched registries;
3. SHA-256 bindings match the exact registry bytes;
4. link IDs exist in the corresponding registries;
5. pairs are ordered/unique and seasonal/evergreen compatibility is valid.

Any mismatch is a fail-closed discovery condition: keep broad Category
navigation and gallery/detail/print working, but do not invent or infer
Category↔Topic relationships from labels, titles, catalog usage or legacy terms.

Because these are same-origin resources, the browser does not need a CORS
exception. MDN documents that cross-origin `fetch()` needs CORS while
same-origin requests do not. For freshness, prefer normal HTTP revalidation
(`cache: "no-cache"`) when the public server supplies validators; `no-store`
is stricter but bypasses storage and should not be required merely to work around
taxonomy drift.

References:

- MDN Fetch API: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch
- MDN Request cache modes: https://developer.mozilla.org/en-US/docs/Web/API/RequestInit
- W3C APG disclosure pattern: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/

The projection only supplies hierarchy data. The public UI should keep its
native/accessible Category disclosure behavior and preserve broad no-JavaScript
Category links.

## Source mutation invariant

After the projection has been seeded, protected ADMIN mutations for Categories,
Topics, or Category↔Topic links require the existing projection to exactly match
the current three canonical registries before the first write.

A successful mutation stages both the changed canonical registry and the new
public projection before replacing either target. After the first staged
filesystem mutation, every error is terminal STOP under the existing policy:
no automatic retry, rollback, cleanup or alternate API loop.

This has two effects:

- a missing or stale projection cannot silently permit further taxonomy writes;
- a post-first-write interruption is preserved as evidence and blocks later
  mutation until manually reviewed.

Read-only ADMIN requests never create, repair or overwrite the public file.

## Initial materialization

Source operator:

```text
scripts/ausmalwiese_category_topic_public_projection_v1.py
```

Its paths are fixed. `--plan` is read-only and reports only bounded hashes,
revisions, link count and target. `--apply` requires an exact confirmation and
may create the projection only when the target is absent. If an existing target
differs, it stops for manual review rather than overwriting it.

The future LIVE order is intentionally separate from this source issue:

1. merge reviewed source;
2. fresh exact-main/runtime preflight;
3. separately owner-authorized source sync if required;
4. read-only projection `--plan`;
5. separately owner-authorized one-shot projection materialization;
6. verify public `/category-topics.json` exact bytes/hash;
7. only then install/activate any ADMIN backend source that requires the
   projection as a mutation precondition;
8. public `coloring-pages#507` consumer rollout remains a separate repo/LIVE
   decision.

#1464 itself authorizes none of those LIVE steps.
