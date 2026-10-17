# Ausmalwiese Stats privacy D1 migration planner (#1061)

**SOURCE ONLY / NO MERGE / NO LIVE / NO D1 WRITE / NO CREDENTIAL ACCESS.**

## Purpose

This planner prepares the first runtime gate required by the merged privacy
backend in `coloring-pages`. It does not execute Wrangler or contact
Cloudflare.

Frozen application source:

- `coloring-pages/main`:
  `699c036b7f952aa98be06e166a9705069b7e9eb2`
- Worker blob:
  `94e802ce145dd75f5701c4c9274a4ac7959c7f5e`
- Wrangler config blob:
  `3733263a391274f2b6b0f2023c8656565bde8e1a`
- additive migration blob:
  `b5346c05cb27de1010dab2027b0b923e999af775`
- later legacy cleanup blob:
  `a7cffb110adfceb5c1ff4dcd17a7009c549976a5`

Target D1 is the existing `DB` binding for
`coloring-pages-stats-v1`, database ID
`f8ac8f1d-a230-4bc4-af13-557c1b91b273`.

## Official Wrangler contract

Cloudflare documents `wrangler d1 execute <DATABASE> --remote --file <file>`
for applying a SQL file to a remote D1 database. `--command` and `--file`
are distinct modes. The source planner therefore freezes a single file-based
mutation and uses separate read-only `--command ... --json` plans for schema
evidence.

Reference:
https://developers.cloudflare.com/d1/wrangler-commands/

## Trusted preconditions

Before any future D1 mutation, the operator must have fresh authenticated
evidence normalized through the existing Stats Wrangler inventory boundary.
The inventory must still prove:

- exact Worker and Production target;
- latest uploaded version equals the one active version at 100%;
- expected script/API conflict source;
- exact D1 binding/database identity;
- exact Rate Limiter, secret-name set, compatibility settings and plain-variable
  fingerprints;
- privacy source provenance:
  `699c036b7f952aa98be06e166a9705069b7e9eb2` and Worker blob
  `94e802ce145dd75f5701c4c9274a4ac7959c7f5e`.

The protected inventory runtime must itself be upgraded through issue #1060
before that future evidence can be used. #1061 does not install or upgrade it.

## Schema evidence

The future read-only adapter normalizes three fixed target objects:

- table `like_cookie_sessions` with exactly:
  `cookie_hash TEXT` primary key,
  `consent_notice_version INTEGER`,
  `consent_recorded_at TEXT`,
  `expires_at INTEGER`;
- table `archived_like_totals` with exactly:
  `page_id TEXT` primary key and `like_count INTEGER`;
- index `idx_like_cookie_sessions_expiry` on
  `like_cookie_sessions(expires_at)`.

Before the mutation all three target objects must be absent. If any already
exists, STOP rather than treating the state as permission to retry or repair.

The owner gate must bind the trusted inventory SHA-256, the pre-schema
SHA-256, the exact database ID, source commit and migration Git blob.

## One future mutation

Only after those proofs, the planner can return this exact command shape as
data:

    npx --yes wrangler@4.135.0 d1 execute DB --remote       --file cloudflare/stats-cookie-like-migration.sql --yes       --config cloudflare/wrangler.stats-worker.jsonc

The future runtime must independently prove that the config and migration file
bytes match the frozen Git blobs immediately before dispatch.

The command must not use arbitrary `--command` SQL, a caller-provided path,
another database, `--local`, `--preview`, or the cleanup migration.

After dispatch, any error, timeout or ambiguous result is terminal STOP. Project
policy intentionally forbids automatic retry/rollback/cleanup even though
provider documentation may describe database rollback behavior.

## Postcondition

Read-only schema evidence must then match the exact semantic target shape.
Only after this D1 gate is verified may the separately authorized one-time
Worker takeover/upload/deploy gate proceed.

Cron activation and
`cloudflare/stats-remove-daily-visitor-hmac.sql` remain later independent
owner gates.

Passing this source test/contract is **not LIVE evidence**.
