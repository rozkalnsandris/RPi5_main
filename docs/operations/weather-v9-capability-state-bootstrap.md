# Weather v9 capability-state bootstrap recovery

Issue: #623

This recovery exists only for the partial Weather v9 capability installation where the reviewed privileged capability artifacts are already installed and exact, while both canonical durable state objects are absent.

## Preconditions

- `registration.json` is absent.
- `state.sqlite3` is absent.
- Fixed staging paths are absent.
- Installed support module, broker, socket unit and service unit are root-owned, single-link regular files with their reviewed modes.
- The installed support module exposes the canonical `StateStore` bootstrap implementation.

Any mixed state, already-complete state, symlink/type/ownership/mode drift, or staging residue is a hard failure.

## Allowed mutation

The recovery may create the canonical replay DB only through `StateStore(..., bootstrap=True)`. After successful DB bootstrap and validation it may publish the canonical root-owned `0600` registration. Registration is the final publication step.

It does not replace installed capability artifacts, invoke `systemctl`, mutate Docker/network/Cloudflare, touch credentials, alter the manager checkout, migrate or clean an existing DB, or perform retry/rollback/cleanup.

## Failure semantics

After the first state mutation, any error is terminal for that attempt. Preserve evidence and stop; no automatic retry, cleanup or rollback is authorized.

Merge of this source does not authorize LIVE execution. A fresh read-only runtime preflight and separate owner LIVE authorization remain required.
