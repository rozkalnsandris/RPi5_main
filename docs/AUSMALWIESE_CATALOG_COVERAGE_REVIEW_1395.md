# Ausmalwiese Catalog coverage review (#1395) — source-only

## Scope and authority

The existing protected `Catalog → Review classifications → Analyze Catalog` implementation from #1341 is extended, not replaced. This is a **review UI and a deterministic DRY_RUN_ONLY manifest**, not a bulk catalog editor, public release, migration, registry editor or authorization to read protected runtime data.

No real catalog entries, archives, category/topic registries, PNGs, publication jobs, permissions, private credentials or runtime processes are modified by this feature or by merging its source. A fresh, separately authorized LIVE operation is needed for any subsequent production catalog write (follow-up #1396).

## Complete snapshot and fail-closed review

1. In the protected ADMIN Catalog page, `Analyze Catalog` requests the **entire** published catalog (not the 24-item visible page) and exact deployed taxonomy, managed Categories, managed Topics and Category↔Topic associations.
2. All five sources are read twice with `GET` and no-cache headers. The tool checks canonical SHA validators, counts, unique 7-digit IDs, exact category/topic identities and link compatibility. Digest drift, missing or unsafe memberships, duplicate IDs or inconsistent registries stop the review. Archive entries are not classified.
3. Each unique published ID begins **pending**, even if it already has valid Categories and Topics. A missing Topic is explicitly **Needs review**; a title word is never treated as image-proof. Existing valid ordered Categories/Topics are preserved unless a reviewer deliberately changes them.
4. Each ID supports visible current vs suggested metadata, an existing thumbnail reference, native checkboxes for one or more Categories and all linked/previously-selected Topics, and explicit `Approve`, `Reject` or `Defer`. The first selected Category is the primary. No invalid, unknown, unlinked or empty Topic selection can be approved. Changing Categories does not silently remove Topics, and an incompatible Topic remains visible until the reviewer corrects or defers it.
5. Repeated unmatched title words appear as an **evidence-gathering queue only** (at least two distinct IDs, capped at 20). The labels, seasonality, licensing/character context and Category associations of any new Topics or Categories require separate human research and approval; the UI does not auto-create a taxonomy entry.
6. The export contains **all** unique IDs and their per-ID review decision, ordered before/after memberships, rationale, existing catalog/taxonomy/association SHA digests, coverage counters and bounded candidate word counts. Only **approved changed** rows appear in `approved_changes`. Rows still pending make `complete_review: false`. The export is `ausmalwiese.catalog-classification-review.v2` / `DRY_RUN_ONLY` and never posts or applies anything.

### Editorial policy

For each page, inspect the thumbnail and German title together; human judgment decides the actual motif, not substring heuristics. Prefer existing valid Topics. Assign seasonal Topics only with `jahreszeiten`, and evergreen Topics only under a linked nonseasonal Category. Multiple Categories/Topics are allowed where justified; keep one activity record and ID even for ordered multi-page activities. For protected characters, ambiguous seasonal motifs or mismatched thumbnail/title, select **Defer** and record a safe explanation outside the automated title matcher. Do not create redundant Topics just to force 100% coverage.

**Review completeness** is not the same as successful automatic classification: `published === reviewed` means the reviewer made an explicit choice for every ID; deferred entries remain unresolved and require follow-up. `complete_review` is not authorization to write to LIVE. The future #1396 operator must independently validate this source-only manifest, require separate exact owner approval, recheck current hashes and reject unreviewed/unsafe changes.

## Test evidence and prerequisites

Synthetic offline regression: `node tests/test-coloring-pages-admin-classification.cjs`. Cases include all-ID coverage, ambiguous title phrases, missing/unlinked Topics, multi-Category and multi-Topic selection, preservation of legacy assignments, real edit decisions, invalid approval, repeated unmatched terms, all-five-source read consistency, stale hash rejection and **GET-only / no POST**.

**Before attempting actual protected review:** independently verify that this source is installed in the protected ADMIN UI under its own exact LIVE approval. A GitHub PR/merge does not prove installed state. Obtain only separately authorized read-only protected catalog/registry evidence; historical 477+ figures and V1 seed registries are not current LIVE proof.

## Research references

- [GOV.UK — Checkboxes](https://design-system.service.gov.uk/components/checkboxes/) (multiple selection and fieldset/legend).
- [Google Search Central — site navigation](https://developers.google.com/search/docs/specialty/ecommerce/help-google-understand-your-ecommerce-site-structure) (meaningful category links, not topic proliferation).
- [MDN — If-Match](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-Match) (fresh strong validator before independently authorized application).
