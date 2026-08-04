# V01 safe inventory contract

`scripts/collect-safe-inventory.sh --output DIR` creates one uniquely named UTC result directory below this repository's ignored `evidence/` or `exports/` tree. It refuses root execution, path escapes, and symlinked output paths. Results are private to the invoking user.

The collector uses an explicit read-only command allowlist with timeouts, output limits, and sanitization. It may collect high-level OS, hardware, storage, package, systemd, Docker, socket, journal, repository-state, and local-interface metadata. Docker collection uses formatted listings only; it never uses inspect or reads labels. Repository state is restricted to the three paths named in the V01 task.

The collector does not read process or container environments, raw configuration, raw cron data, key material, database data, backups, browser/session data, shell history, Docker volumes, or application trees. Optional commands may be absent; every attempted section records command availability and an exit status.

Each result contains:

- `summary.json`: machine-readable collector metadata and per-section status;
- `section-status.tsv`: deterministic status table;
- `sections/`: bounded and sanitized text outputs;
- `file-inventory.txt`: deterministic file list;
- `SHA256SUMS`: checksums for every generated file except itself.

Run `scripts/verify-safe-inventory.sh RESULT_DIR` before relying on a result. The verifier enforces the output boundary, ownership and modes, regular-file-only structure, size/count limits, expected metadata, checksums, status completeness, and a no-secret scan. It does not print matched values.
