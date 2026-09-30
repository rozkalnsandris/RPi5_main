# Weather v9 predecessor durable-state bootstrap

Issue: #625

This recovery corrects the ordering defect discovered after #623/#624. The live Weather v9 capability still has the exact predecessor broker from `80261255b3be2aa7dd40986254d4ea478b4e2e1b`, while both durable state objects are absent. The post-#83 broker refresh cannot run until predecessor-bound registration and replay state exist.

## Accepted baseline

The recovery accepts only:

- `registration.json` absent;
- `state.sqlite3` absent;
- all 15 installed host-capability artifacts byte-identical to predecessor `80261255...`, with exact modes, root ownership, single-link regular-file semantics and rendered service identity;
- all known refresh/bootstrap staging paths and SQLite sidecars absent;
- exact config/state directory metadata;
- a clean reviewed-origin execution checkout that descends from the predecessor.

The execution checkout SHA is **not** written into registration. Registration is deliberately bound to predecessor `80261255...`, because that is the installed artifact identity the already-reviewed post-#83 broker refresh expects.

## Allowed mutation

A later separately authorized `--apply` may:

1. create the fixed state root as root-owned `0700` only if absent;
2. create the replay DB only through canonical `StateStore(..., bootstrap=True)`;
3. verify the DB through ordinary `StateStore` open;
4. publish the strict root-owned `0600` predecessor-bound registration last.

No installed capability artifact is replaced. No `systemctl`, Docker, network, Cloudflare, secret, manager-checkout, existing-DB migration, retry, cleanup or rollback path is added.

## Required gate order

1. merge this source and require exact-main CI green;
2. if the exact reviewed source commit is absent on RPi5, use a separate bounded LIVE authorization only to materialize that exact source;
3. run canonical predecessor-bootstrap preflight read-only;
4. obtain a separate owner LIVE authorization for one predecessor state-bootstrap apply;
5. verify registration and replay state;
6. run the already-merged post-#83 broker-refresh preflight;
7. obtain a separate owner LIVE authorization for broker + registration refresh;
8. only then resume Weather v9 queue/dispatch/public-runtime reconciliation.

Any failure after the first mutation is fail-closed. No automatic retry, cleanup, rollback or alternate mutation is authorized.
