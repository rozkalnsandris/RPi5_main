# Roadmap

## V01 — safe inventory foundation

Create a strictly read-only collector that records only approved metadata:

- OS, kernel and architecture
- filesystem and block-device summary
- enabled systemd unit names
- systemd timer names and schedules
- Docker container names, images, states and health only
- Docker Compose project names only
- listening TCP/UDP ports without process environments
- package inventory
- failed systemd unit names
- basic backup job presence without backup contents

The collector must not read environment variables, container inspect environments,
credentials, database contents, private keys, raw Cloudflare configuration or Docker volumes.

## V02A — complete: least-privilege access-model diagnostic

V02A added a bounded diagnostic and verified standard/approved-context comparison for Docker, systemd, socket, and interface metadata access. It made no host changes. See [V02A findings](V02A_FINDINGS.md).

## V02B — complete: verified runtime baseline

V02B adds a bounded host-equivalent read-only runtime collector, verifier, renderer, and a sanitized tracked baseline bound to verified evidence. It does not change Docker access, permissions, services, or production configuration. See the [runtime baseline contract](V02B_RUNTIME_BASELINE_CONTRACT.md) and [current baseline](CURRENT_RUNTIME_BASELINE.md).

## V03 — complete: deterministic offline runtime diff

V03 compares two verified V02B JSON baselines with strict input/report validation and deterministic JSON/Markdown output. It is offline-only and does not collect, monitor, alert, deploy, remediate, or alter the host. See the [diff contract](V03_RUNTIME_DIFF_CONTRACT.md) and [findings](V03_FINDINGS.md).

## V04 — complete: controlled baseline review tooling

V04 validates a manually supplied canonical candidate, requires a deterministic V03 diff, records an explicit human decision, and permits promotion only for the exact reviewed, strictly newer candidate with an `accepted` decision. Previous current baselines are archived with checksummed transition records. V04 does not schedule collection, accept changes automatically, deploy, remediate, or alter the host. See the [review contract](V04_BASELINE_REVIEW_CONTRACT.md) and [findings](V04_FINDINGS.md).

## V05 — complete: first reviewed temporal refresh

V05 collected a second read-only host snapshot, verified and rendered it, produced a V03 diff, recorded an explicit accepted V04 decision, archived the previous current baseline, and promoted the exact reviewed candidate. No host state was changed by the review or promotion workflow. See the [V05 findings](V05_FINDINGS.md).

## V06 — complete: dynamic runtime semantics

V06 introduces a backward-compatible v2 diff schema. Exact high-numbered socket and dynamic `veth` observations remain auditable, while stable-profile rotation is grouped into one semantic change. Stable/low-port socket changes and non-`veth` interface changes remain material. Archived v1 reports remain valid. See the [V06 contract](V06_DYNAMIC_RUNTIME_SEMANTICS.md) and [findings](V06_FINDINGS.md).

## V07 — complete: end-to-end baseline lineage verification

V07 verifies the archive as one continuous and acyclic sequence of accepted transitions. Every archived old binding must match its stored baseline, every transition must begin at the previous transition head, and the final head must equal the exact canonical current JSON and deterministic Markdown projection. It emits optional deterministic JSON/Markdown integrity reports below ignored evidence paths and performs no host collection or mutation. See the [V07 contract](V07_RUNTIME_LINEAGE_CONTRACT.md) and [findings](V07_FINDINGS.md).

## V08 — tooling complete: bounded memory-pressure diagnosis

V08 implements the non-root, read-only collector and verifier for issue #5. It measures MemAvailable, retained and active swap signals, memory PSI, major faults, safe process-name RSS totals, current container memory and bounded kernel memory events without reading arguments, environments, DNS queries or application configuration. A real RPi5 bundle and evidence-based root-cause conclusion remain post-merge work. See the [V08 contract](V08_MEMORY_PRESSURE_DIAGNOSTIC_CONTRACT.md) and [findings](V08_FINDINGS.md).

## V09 — complete: deterministic memory-pressure series analysis

V09 verifies and analyzes two to sixty-four chronological V08 bundles offline. It normalizes Docker memory strings to KiB, fixes the observed 1024× MiB rendering error, reports host and per-container trends, and classifies isolated activity separately from sustained pressure. Source bundles remain unchanged and generated reports stay below ignored evidence paths. See the [V09 contract](V09_MEMORY_PRESSURE_SERIES_CONTRACT.md) and [findings](V09_FINDINGS.md).

## V10 — source ownership import: encrypted host backup

V10 imports the existing host-wide encrypted backup script, configuration example, cron entry, and logrotate entry from the Hermes Tech repository without changing their bytes. Source Git blobs and SHA256 values are pinned in CI, and the source-to-installed mapping, no-op verification gate, future deployment controls, and rollback are documented. No host verification, backup execution, scheduling change, upload, retention deletion, restore, or deployment is performed by the repository import. See the [V10 contract](V10_BACKUP_OWNERSHIP_CONTRACT.md) and [findings](V10_FINDINGS.md).

## V11 — tooling complete: AdGuard memory attribution

V11 identifies exact `AdGuardHome` processes and attributes their memory using PSS, cgroup-v2 and RSS fallback data. It separates anonymous, file-backed, shared, kernel/socket, slab and swap classes, reports container-limit headroom, and preserves strict privacy by excluding process IDs, cgroup paths, DNS queries, client identities, arguments, environments and raw configuration. At least four verified live samples are required before the AdGuard root-cause conclusion is updated. See the [V11 contract](V11_ADGUARD_MEMORY_ATTRIBUTION_CONTRACT.md) and [findings](V11_FINDINGS.md).

## Later phases

Each subsystem is imported separately with redaction, tests, rollback instructions and a pull request.
