# Weather v9 capability-state bootstrap recovery

Issue: `RPi5_main#623`  
Status: **SOURCE-ONLY / LIVE LATER**

This recovery exists only for the observed partial Weather v9 privileged host-capability installation where all reviewed installed artifacts are exact while both canonical durable state objects are absent:

- `/etc/rozkalns-weather-operator-v9-capability/registration.json`
- `/var/lib/rozkalns-weather-operator-v9-capability/state.sqlite3`

## Read-only preflight

The recovery reuses `scripts/install-weather-operator-v9-host-capability.py` as the canonical source of the 15-artifact installation closure. It requires the source checkout and canonical `RPi5_main` manager provenance to remain clean/read-only and verifies every installed artifact as a single-link root-owned regular file with its reviewed mode and exact expected bytes. The rendered systemd service unit is compared against the canonical installer rendering, not the unrendered repository template.

The config root must already be an exact root-owned `0700` directory. The state root may be absent or an exact root-owned `0700` directory. Any registration/state mixed state, already-complete state, symlink/type/owner/mode/byte drift, duplicate installer target, known refresh/bootstrap staging residue, or SQLite `-wal`/`-shm` residue fails closed before mutation.

## Bounded mutation

A later separately authorized root `--apply` may only:

1. create the fixed state root as root-owned `0700` when it is absent;
2. create the replay database through canonical `StateStore(STATE_DB_PATH, bootstrap=True)`;
3. set the newly-created DB to root-owned `0600`, fsync it and reopen it through normal `StateStore` integrity verification;
4. stage a strict 10-field registration and atomically publish it as root-owned `0600` **after** the DB is valid.

The registration schema is `rozkalns.rpi5-main.weather-operator-upgrade-v9-host-capability-registration.v1` and binds the exact reviewed source SHA, canonical manager checkout/UID/GID, artifact count `15`, and the exact module/broker/socket/rendered-service hashes.

No installed capability artifact is replaced. There is no `systemctl`, Docker, networking, Cloudflare, secret/credential, manager-checkout, existing-DB migration/cleanup, worktree cleanup, retry, rollback or alternate mutation path.

## Failure semantics

After the first authorized mutation begins, any error is terminal for that attempt. Preserve minimum public-safe evidence and STOP; do not retry, clean up, roll back or select an alternate mutation without a new explicit owner authorization.

Merge of this source never authorizes LIVE execution. After merge and exact-main CI, a fresh read-only runtime preflight and separate exact LIVE authorization are still required.
