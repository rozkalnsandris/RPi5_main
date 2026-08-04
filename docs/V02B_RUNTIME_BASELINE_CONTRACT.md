# V02B verified runtime baseline contract

V02B is a fixed, read-only runtime inventory. It may run only as a non-root user in an explicitly approved host-equivalent context. It does not alter Docker, systemd, networking, packages, access control, configuration, or runtime data.

`scripts/collect-runtime-baseline.sh --output DIR --context LABEL` creates a private, unique `v02b-*` result below ignored `evidence/` or `exports/`. Every one of the fixed Docker, systemd, socket, and interface sections records command presence, exit code, classification, timestamps, byte count, and context. The collector stores only safe projections, has fixed timeouts and size bounds, rejects output-path symlinks, and binds the result to its source Git commit.

`scripts/verify-runtime-baseline.sh RESULT_DIR` enforces the exact file tree, ownership and mode constraints, regular-file-only evidence, checksums, metadata, status completeness, field schemas, bounds, and redaction policy. It rejects raw IP/MAC addresses, raw Compose configuration, environment and systemd execution fields, Docker IDs, credentials, tokens, private-key material, and unexpected artifacts without printing sensitive matches.

`scripts/render-runtime-baseline.py` first invokes the verifier and then renders deterministic `baselines/runtime/current.json` and `docs/CURRENT_RUNTIME_BASELINE.md`. The tracked files contain only the approved normalized inventory, collection metadata, evidence-manifest SHA-256 binding, and capability limitations. They are a snapshot, not deployment configuration or a causal diagnosis.

The systemd `is-system-running` projection treats `running` as success. Recognized informational non-zero states such as `degraded` are retained as the normalized state and classified `success_degraded`; V02B does not inspect logs or infer their cause.
