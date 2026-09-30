# Weather data companion reconciliation

Issue #684 separates the historical public-corpus bootstrap contract from ordinary post-bootstrap recurring ingest.

The historical bootstrap remains pinned to the reviewed Weather consumer source `789a79820807829cc9b057d9ffafc56e0e41afe9` and its original bounded bootstrap window. That pin is not reused as a recurring-enable requirement after later ordinary SIMPLE-DEPLOY application releases.

Post-bootstrap recurring readiness instead requires the current reviewed SIMPLE-DEPLOY target/image/runtime identity, `/ready=200`, the timer and service to remain disabled/inactive before enable, an unchanged production pointer, and corpus integrity for the canonical fixed benchmark window `2026-08-13..2026-08-26`.

`corpus-report` state `PASS` is accepted. `WARN` is accepted only when `block_reasons` is exactly empty and warning reasons are explicit non-empty strings. `BLOCKED`, malformed warning output, or `corpus-check ok != true` remains fail-closed. This permits known non-blocking model-version warnings without weakening coverage, provenance, run-count, pointer or database-integrity checks.

The installed companion is reconciled with `scripts/reconcile-simple-deploy-weather-data-v1.py`. The source path is deliberately one-time and capability-specific: it freezes predecessor `RPi5_main@7be2772ca8c0dddefd00181c805bd693bc06a9ed`, requires every tracked installed artifact to match the exact predecessor bytes and root-owned metadata before mutation, and atomically replaces only tracked artifacts whose reviewed bytes changed. Unknown preimage or metadata drift fails before mutation.

The reconciliation script does not run `systemctl`, Docker, application commands, database/corpus operations, cleanup, delete or rollback. It does not enable or start the recurring timer. Source merge does not execute reconciliation and does not authorize LIVE.

After merge, the next sequence is:

1. fresh read-only host/source/preimage verification;
2. separate exact owner LIVE authorization for the reviewed companion reconciliation only;
3. post-reconciliation read-only `--enable-preflight`;
4. separate exact owner systemd gate to enable/start `rozkalns-weather-public-ingest.timer` and verify the first bounded ingest.

Any error after the first authorized reconciliation write consumes that LIVE authorization and requires STOP without automatic retry, rollback, cleanup or alternate mutation.
