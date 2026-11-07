# Ausmalwiese Stats legacy-ID migration v1 — issue #1412

SOURCE ONLY / NO MERGE / NO LIVE / NO D1 WRITE / NO CREDENTIAL ACCESS.

## Purpose

Prepare the Stats-side prerequisite for the later Ausmalwiese catalog/media ID cutover.
The canonical old-to-new mapping remains coloring-pages issue #457. RPi5_main vendors
the exact reviewed alias JSON bytes only as an immutable input; the planner requires
Git blob 2e20a2a7a7e716274934a0eb662091150ef55e7f before parsing, so there is no second
hand-edited mapping.

Upstream identity is coloring-pages commit
9c013bfbab8f3cc5eaaa905f57119c53abc8ab48, catalog SHA-256
efa6a736839657f849606f665b09bd51dff1165a1c9c2038e9d5b7e720cc7ba9,
plan SHA-256 80538dd2bda9755212c599d1b75a106673e1eb5c774cebc47f4192e0478fad9c,
and alias-list SHA-256 24cf6ec46ba2ad2b1791c8aff8975937bb9b0e629076d0d34b828ee30d6308b5.

## Exact D1 scope

The reviewed target is DB / coloring-pages-stats-v1 /
f8ac8f1d-a230-4bc4-af13-557c1b91b273.

All current page_id tables are in scope: page_stats, daily_prints, likes,
daily_views, daily_campaign_events and archived_like_totals. daily_print_qr_scans
and like_cookie_sessions contain no page identity and stay unchanged.

The contract also pins Worker blob 8790a8ddc3b83771088c4cceb16a3b57ce5d1c8b,
Wrangler config blob 3733263a391274f2b6b0f2023c8656565bde8e1a and schema blob
ead4cc5f497de6eeac0cf6b07c2ca13db986423a. Later source/schema drift requires a
new review before any mutation.

## Sanitized preflight and post-read

The evidence schema contains only exact source/database/alias identities, public page
IDs, table column/type/PK shapes, row counts, aggregate counter sums and unrelated row
counts. It must never expose visitor_hash, timestamps, raw rows, credentials or secrets.

Before mutation every one of the 30 target IDs must have zero rows in every page_id
table. Alias drift, target collision, schema drift or database/source identity drift is
a hard STOP.

After a separately authorized migration, validate_post requires zero legacy rows,
the corresponding target row counts and counter sums to match exactly, and unrelated
row counts to stay unchanged. Offline SQLite tests additionally prove every non-ID
column is preserved for all 30 mappings and both explicitly untouched tables.

## One transaction

migration_operation emits one operation object with transaction D1_DATABASE_BATCH and
exactly six fixed UPDATE statements. Each statement derives all 30 pairs from the
validated vendored alias artifact and changes only page_id. There is no caller-provided
SQL/table/database and no merge-on-collision behavior.

Cloudflare documents D1 batch() as transactional: prepared statements execute in
sequence and the sequence is rolled back if a statement fails:
https://developers.cloudflare.com/d1/worker-api/d1-database/#batch

This source does not implement a credentialed Cloudflare executor.

Required order:
fresh sanitized D1 preflight -> separate owner-authorized one-shot D1 batch ->
sanitized D1 post-verification -> separate RPi5 catalog/media ID cutover.

Do not reverse that order. Public Stats already contains non-zero legacy-ID state, so
changing catalog IDs first could split user-visible counts.

## Authority boundary

Merge of this source performs no Cloudflare request, D1 read/write, credential access,
Worker upload/deploy, RPi5 content mutation, service lifecycle action or redirect-marker
activation. Actual D1 migration and later catalog/media cutover each require separate
exact owner authorization. Retry, rollback and cleanup are not authorized here.
