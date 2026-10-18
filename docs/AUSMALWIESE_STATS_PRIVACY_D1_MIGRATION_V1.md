# Ausmalwiese Stats privacy D1 migration planner (#1061, reconciled by #996)

**SOURCE ONLY / NO MERGE / NO LIVE / NO D1 WRITE / NO CREDENTIAL ACCESS.**

## Purpose

This planner prepares Gate A for the merged privacy backend. It does not execute
Wrangler, contact Cloudflare or mutate D1.

Reviewed application source:

- `coloring-pages/main`:
  `7f07c226105e26c0ca9cf91eb150a3e8f585c5ea`
- Worker blob:
  `c2ac9da6e0701103e0041b30db7dfbea4298f96c`
- Wrangler config blob:
  `3733263a391274f2b6b0f2023c8656565bde8e1a`
- additive migration blob:
  `b5346c05cb27de1010dab2027b0b923e999af775`
- later legacy cleanup blob:
  `a7cffb110adfceb5c1ff4dcd17a7009c549976a5`

Target D1 is the existing `DB` binding for
`coloring-pages-stats-v1`, database ID
`f8ac8f1d-a230-4bc4-af13-557c1b91b273`.

## Why Gate A has its own remote evidence contract

Issue #996 exposed a real remote state that the old Gate A precondition could
not represent:

- one active version remains at 100% traffic;
- the latest uploaded version can differ from the active version;
- the active version can predate the reviewed privacy Worker;
- `VISITOR_HMAC_KEY` can be absent from that active version even though the
  reviewed Wrangler config still names it for later compatibility takeover.

Those facts block a Worker takeover, but they do **not** make an additive,
unused D1 schema preparation unsafe by themselves. The migration creates new
objects that the current active Worker does not use.

Gate A therefore consumes the bounded
`ausmalwiese.stats-gate-a-remote.v1` evidence instead of the strict takeover
inventory. It still requires:

- exact Production Worker target and Wrangler version;
- exactly one active version at 100% traffic;
- valid bounded active provenance;
- only known binding names/kinds, with `DB:d1` required;
- exact reviewed app commit, Worker blob, config blob and migration blob;
- exact D1 database identity from the reviewed config/schema evidence;
- all three target schema objects absent;
- an owner gate binding both the remote-evidence SHA-256 and pre-schema
  SHA-256.

Gate A deliberately does **not** require `latest == active` and does **not**
require `VISITOR_HMAC_KEY` to exist on the currently active version. If the
secret is present, only its name/kind may appear; its value is never read.

This relaxation is limited to additive D1 Gate A. The later Worker
upload/deploy Gate B remains strict and must independently prove the bindings,
settings, routes, exact source and deployment transition it needs.

## Official Wrangler contract

Cloudflare documents `wrangler d1 execute <DATABASE> --remote --file <file>`
for applying a SQL file to a remote D1 database. `--command` and `--file`
are distinct modes. The source planner therefore freezes a single file-based
mutation and uses separate read-only `--command ... --json` plans for schema
evidence.

Reference:
https://developers.cloudflare.com/d1/wrangler-commands/

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

Before mutation all three target objects must be absent. If any already exists,
STOP rather than treating the state as permission to retry or repair.

The owner gate must bind the sanitized remote evidence SHA-256, the pre-schema
SHA-256, the exact database ID, current reviewed source commit, source/config
blobs and migration Git blob.

## One future mutation

Only after those proofs, the planner can return this exact command shape as
data:

    npx --yes wrangler@4.135.0 d1 execute DB --remote --file cloudflare/stats-cookie-like-migration.sql --yes --config cloudflare/wrangler.stats-worker.jsonc

The future runtime must independently prove that the config and migration file
bytes match the frozen Git blobs immediately before dispatch.

The command must not use arbitrary `--command` SQL, a caller-provided path,
another database, `--local`, `--preview`, or the cleanup migration.

After dispatch, any error, timeout or ambiguous result is terminal STOP. Project
policy forbids automatic retry/rollback/cleanup even though provider
documentation may describe database rollback behavior.

## Postcondition

Read-only schema evidence must then match the exact semantic target shape.
Only after this D1 gate is verified may the separately authorized Worker
upload/deploy gate proceed.

Cron activation and
`cloudflare/stats-remove-daily-visitor-hmac.sql` remain later independent owner
gates.

Passing this source test/contract is **not LIVE evidence**.
