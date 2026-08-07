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

## V12 — controlled host deployment

V12 adds a normal-user VS Code controller and a separately confirmed, versioned, root-owned deploy engine. The engine is installed below `/usr/local/libexec/rpi5-deploy/releases/<commit>/`; the active root wrapper starts with `env -i`, and every privileged command verifies installed engine SHA/UID/GID/mode. Plan, deploy and status additionally require current tracked engine-source hashes; rollback and logs remain available through the verified installed engine during repository-source drift.

The operator commands are `sync`, `test`, `install-engine`, `engine-status`, `plan`, `deploy`, `status`, `rollback` and `logs`. The initial target set remains exactly the three non-secret V10 backup implementation files. The private `/etc/rpi5-backup.conf` is reference-only.

A 30-minute plan binds exact `main`, `origin/main`, exact-commit GitHub checks, RPi5 host and runtime health, backup freshness, the manifest hash, source hashes and complete before/desired SHA-256, UID, GID and mode fingerprints. Apply creates private transaction backups, records phases durably, uses same-directory replacement with fsync, validates after each write and automatically rolls back any partial failure. Manual rollback refuses later content or metadata drift.

Merging V12 does not install the engine or deploy to the host. Engine installation, live plan review and any production apply are separate explicit post-merge actions. See the [V12 contract](V12_CONTROLLED_DEPLOY_CONTRACT.md) and [findings](V12_FINDINGS.md).

## V13 — Cloudflare Tunnel host ownership

V13 imports the non-secret systemd source and operating contract for the shared `rpi5-tunnel` connector. Cloudflare remains remotely managed; `RPi5_main` becomes authoritative for the RPi5 connector runtime while application repositories are forbidden from controlling the shared tunnel lifecycle.

The reviewed service pins `cloudflared 2026.7.3`, consumes the root-only token through systemd `LoadCredential=` and `--token-file`, exposes diagnostics/Prometheus metrics only on loopback, uses bounded resource controls and retains the networking required to reach Cloudflare edge and local origins. CI includes the ownership contract plus `systemd-analyze verify` against a production-path-neutralized copy of the unit.

The migration is explicitly no-downtime: the existing Docker connector remains online until the new host connector independently proves four active edge connections and all published applications pass end-to-end checks. The temporary Docker container IP used by the apex route is not a final origin. Token rotation, UFW cleanup, CV ownership removal, monitoring integration and later Terraform control-plane import are separate post-cutover gates.

Merging V13 performs no production mutation. Installing the exact reviewed unit, starting the replica, retiring the old Docker connector and every later cleanup step remain separately confirmed live actions. See the [V13 contract](V13_CLOUDFLARE_TUNNEL_OWNERSHIP_CONTRACT.md).

## Later phases

Each remaining subsystem is imported separately with redaction, tests, rollback instructions and a pull request. Docker Compose, Home Assistant, monitoring, update scripts and application repositories remain outside the V12 target set until their own contracts are reviewed. Cloudflare runtime ownership is defined by V13, but its live cutover and future control-plane-as-code work remain explicitly gated operations.
