# RPi5_main

This private repository is the source of truth for the Raspberry Pi 5 infrastructure.

Configuration is imported incrementally, with each small change reviewed before it can become authoritative. Secrets, private keys, credentials, runtime data, database data, Docker volumes, and backups are never stored in Git.

## Change workflow

Every change follows: **branch → tests → draft PR → CI → review → squash merge**.

Any future production apply must bind to an exact Git commit and include preflight checks, a backup plan, verification, and a documented rollback. It is not enabled by this repository.

## Versions

V01 is inventory-only. Its collector is read-only, creates a bounded and sanitized local evidence bundle, and makes no production changes. Generated evidence remains ignored and untracked.

V02A is complete. It adds a least-privilege, read-only diagnostic that compares approved execution contexts without granting access or changing the host.

V02B is complete. It records a verified, sanitized runtime baseline from the approved host-equivalent read-only context. The tracked baseline is bound to ignored, checksummed evidence and is not deployment configuration.

V03 is complete. It compares two sanitized V02B JSON baselines offline and deterministically; it performs no host collection, monitoring, alerting, deployment, or remediation.

V04 is complete as tooling. It adds an offline, human-gated review, decision, archive, and accepted-only promotion workflow.

V05 is complete. It performed the first real temporal runtime refresh through V02B collection, V03 diff review, an explicit accepted V04 decision, archival of the previous baseline, and promotion of the exact reviewed candidate.

V06 is complete. It adds backward-compatible v2 runtime-diff semantics that retain exact dynamic socket and `veth` observations while grouping stable-profile churn for review.

V07 is complete. It verifies that every accepted archive transition forms one continuous, acyclic lineage ending at the exact tracked current baseline and Markdown projection.

See [the roadmap](docs/ROADMAP.md), [the security model](docs/SECURITY_MODEL.md), [the V01 inventory contract](docs/INVENTORY_CONTRACT.md), [the V02A findings](docs/V02A_FINDINGS.md), [the current runtime baseline](docs/CURRENT_RUNTIME_BASELINE.md), [the V04 review contract](docs/V04_BASELINE_REVIEW_CONTRACT.md), [the V05 findings](docs/V05_FINDINGS.md), [the V06 semantics contract](docs/V06_DYNAMIC_RUNTIME_SEMANTICS.md), and [the V07 lineage contract](docs/V07_RUNTIME_LINEAGE_CONTRACT.md).
