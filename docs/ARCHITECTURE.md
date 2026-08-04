# Architecture

`RPi5_main` is the private, reviewed source of truth for infrastructure-as-code and operational documentation for the Raspberry Pi 5.

V01 has two layers:

- tracked source: collector, verifier, tests, documentation, and CI;
- local ignored evidence: bounded, sanitized inventory results under `evidence/` or `exports/`.

The repository deliberately has no deployment job, self-hosted runner, or production apply mechanism. A future phase may add those only with exact commit binding, preflight, backup, verification, and rollback controls.
