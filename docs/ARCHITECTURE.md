# Architecture

`RPi5_main` is the reviewed GitHub source of truth for Raspberry Pi 5 host-control tooling, infrastructure contracts, tests and operational documentation. GitHub source does not by itself prove the currently deployed RPi5 state.

The repository separates:

- `ops/` — reviewed host operator, deployment, Compose and service source;
- `scripts/` — controlled command entrypoints, installers and offline diagnostics;
- `tests/` and `.github/workflows/` — source, policy and safety verification;
- `docs/` — architecture, trust boundaries, deployment contracts and operational guidance;
- `baselines/runtime/` — approved, sanitized historical runtime baseline lineage.

Locally generated, sanitized diagnostic evidence is ignored by default under `evidence/` and `exports/`. These directories retain their tracked `.gitkeep` placeholders; sensitive runtime data, credentials, backups and raw private configuration must not be committed.

Source changes follow GitHub review and CI. A merge does not authorize host or LIVE mutations. Production operations need the applicable explicit owner authorization and exact target, scope and verification boundaries defined in `AGENTS.md` and `docs/SECURITY_MODEL.md`. Runtime state must be verified separately through the authorized host-control boundary.
