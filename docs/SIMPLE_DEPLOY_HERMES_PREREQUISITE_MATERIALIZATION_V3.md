# Hermes SIMPLE-DEPLOY host-prerequisite materialization v3 recovery

Issue: `#719`  
Status: **SOURCE RECOVERY READY / NOT LIVE**

## Why v3 exists

The first owner-authorized Hermes Composite LIVE used the reviewed v2 materializer from `RPi5_main@2c9a2930df95f206aca28881837ef8888b2a01fb`. Exact trusted source delivery succeeded, but the root v2 `--apply` invocation failed before prerequisite publication because the legacy Hermes `.env` does not contain a prebuilt `DATABASE_URL`.

The legacy `hermes-deals` Compose contract instead builds `DATABASE_URL` from `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`, while consuming `HTTP_USER_AGENT` separately. The same failed invocation also proved that root source validation via `git status` can opportunistically refresh the linked-worktree index: the preserved trusted worktree index became `root:root 0600`, even though v2 reported `mutation_started=false`.

V3 is an additive recovery successor. It deliberately does **not** rewrite v2, repair the failed worktree, or reinterpret the consumed LIVE authorization. The v2 source and failed checkout remain historical evidence.

## Protected env projection

Future v3 `--apply` reads exactly four required values from the fixed legacy `.env` source:

1. `POSTGRES_USER`
2. `POSTGRES_PASSWORD`
3. `POSTGRES_DB`
4. `HTTP_USER_AGENT`

The destination remains exactly two keys in fixed order:

1. `DATABASE_URL`
2. `HTTP_USER_AGENT`

`DATABASE_URL` is derived deterministically as:

`postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@db:5432/{POSTGRES_DB}`

The projection parser is fail-closed. Missing or duplicate required source keys, malformed assignments, unsupported quoting/escapes, empty values and control characters fail without printing values. Destination values are deterministically single-quoted so the private env file remains a literal two-key input to the reviewed API-only Compose adapter. Values, passwords, the derived URL and raw `.env` bytes must never appear in logs or receipts.

CI uses synthetic values only. It never reads production `.env` content.

## Root-safe Git source verification

V3 no longer uses `git status` for checkout cleanliness.

Every Git source-validation process is launched with both:

- Git global option `--no-optional-locks`;
- environment `GIT_OPTIONAL_LOCKS=0`.

Cleanliness is checked read-only with:

- `git diff-files --quiet --`;
- `git diff-index --cached --quiet HEAD --`;
- `git ls-files --others --exclude-standard`.

The validator still requires the exact expected HEAD, canonical origin, clean tracked/index/untracked state, and exact reviewed bytes for the v3 script/contract plus its v2 predecessor dependencies. It grants no index refresh/write, worktree repair, checkout switch/reset, or Git-admin metadata mutation.

Therefore `mutation_started=false` is again truthful for pre-apply source validation: the v3 entrypoint itself has no authorized Git mutation before the existing v2 filesystem apply boundary.

## Inherited Phase-B and publication boundary

V3 does not redesign the already-correct #713/#714 Phase-B model. It reuses v2 for:

- runtime-principal-owned `/var/lib/rozkalns-simple-deployer` mode `0700`;
- `ABSENT / EXACT_READY / PARTIAL_CONFLICT / PRIVILEGED_METADATA_REQUIRED` classification;
- fixed state/config/data destinations;
- no-overwrite staging/publication;
- root-owned materialized children;
- post-mutation evidence preservation;
- no automatic retry, cleanup or rollback.

V3 also reuses the reviewed v1 protected tree copy/digest helpers. Only the two failure surfaces proven by the first LIVE attempt are replaced: source-env projection and Git source verification.

## Preserved failure evidence

The existing trusted checkout identity `RPi5_main-hermes-simple-deploy-first-live-trusted` and its observed root-owned index are preserved exactly as failure evidence. #719 authorizes no `chown`, `chmod`, reset, clean, remove, prune, recreate or alternate worktree path.

After this source recovery merges, any decision to repair or reuse that checkout requires a new exact owner recovery authorization. Source merge itself authorizes neither recovery nor LIVE.

## Tests

The v3 focused suite proves:

- four legacy source keys project to exactly two destination keys in fixed order;
- the derived `DATABASE_URL` follows the reviewed legacy Compose semantics;
- quoted `HTTP_USER_AGENT` input is normalized without exposing protected values;
- missing, duplicate and unsafe values fail closed without secret-bearing errors;
- every Git validator invocation disables optional locking;
- checkout cleanliness uses no `git status` path;
- the existing v2 Phase-B parent and apply semantics remain intact;
- the v3 machine contract preserves the failed checkout as non-repairable evidence;
- CLI authority remains only `--expected-source-sha` and `--apply`;
- CI runs v1, v2 and v3 regressions and never invokes `--apply`.

## Authority and next gate

#719 is source/docs/tests/CI only. AUTO-RUN FULL may deliver and merge the canonical #719 Outcome PR, but merge grants no host recovery or runtime authority.

After merge and exact-main CI success, the next sequence is still separately gated:

1. fresh exact owner recovery decision for the preserved trusted-worktree metadata if repair/reuse is chosen;
2. fresh privileged read-only prerequisite classification;
3. only then a new exact Composite LIVE may be considered, bound to the then-current RPi5 source, Hermes release/digest and v3 protected source-key contract.

No host access, secret read, permission repair, prerequisite materialization, target adoption, Docker/systemd/network/Cloudflare/database mutation, retry, rollback or cleanup is authorized by this source issue.
