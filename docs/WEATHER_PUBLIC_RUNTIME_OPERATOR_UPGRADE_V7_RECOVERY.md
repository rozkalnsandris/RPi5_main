# Weather public runtime operator upgrade v7 recovery

Issue #537 is the source-only successor to the consumed v6 operator-upgrade transaction.

The v6 transaction successfully created its exact detached trusted checkout and then failed before runtime replacement because the v6 source entrypoint was tracked as Git mode `100644`. That checkout and authorization are immutable historical evidence and are never retried, repaired, cleaned, rolled back or reused.

The v7 bridge uses a new fixed checkout identity, accepts no caller arguments, and requires its source entrypoint to be committed as `100755`. The module retains the reviewed one-target transition from installed SHA-256 `4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f` to `f6255bf1e80d2918555b0814b0690add739041ac11512297d904fce5e8fc0cf1`. It retains same-directory exclusive temporary publication, fsync, atomic replace and parent fsync, with no automatic retry, cleanup, rollback or backup restore.

Merging v7 performs no host mutation and creates no trusted checkout. A future owner LIVE authorization must bind the then-current exact `RPi5_main` SHA, the fixed v7 checkout, the predecessor and target hashes, and the same no-retry/no-cleanup/no-rollback semantics. After a successful replacement, installed-closure verification and a fresh sanitized Weather baseline are required before a new Composite STRICT LIVE authorization can be prepared.
