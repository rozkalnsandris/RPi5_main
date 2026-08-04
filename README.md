# RPi5_main

This private repository is the source of truth for the Raspberry Pi 5 infrastructure.

Configuration is imported incrementally, with each small change reviewed before it can become authoritative. Secrets, private keys, credentials, runtime data, database data, Docker volumes, and backups are never stored in Git.

## Change workflow

Every change follows: **branch → tests → draft PR → CI → review → squash merge**.

Any future production apply must bind to an exact Git commit and include preflight checks, a backup plan, verification, and a documented rollback. It is not enabled by this repository.

## V01

V01 is inventory-only. Its collector is read-only, creates a bounded and sanitized local evidence bundle, and makes no production changes. Generated evidence remains ignored and untracked.

See [the roadmap](docs/ROADMAP.md), [the security model](docs/SECURITY_MODEL.md), and [the inventory contract](docs/INVENTORY_CONTRACT.md).
