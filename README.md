<p align="center">
  <img src="assets/branding/project-logo.svg" alt="RPi5 Main project logo" width="128" height="128">
</p>

<h1 align="center">RPi5 Main</h1>

<p align="center">
  <strong>Source-controlled infrastructure for a production Raspberry Pi 5 homelab, with exact-commit deploys and strict secret boundaries.</strong>
</p>

<p align="center">
  <a href="docs/ROADMAP.md">Roadmap</a>
  ·
  <a href="docs/SECURITY_MODEL.md">Security model</a>
  ·
  <a href="docs/CURRENT_RUNTIME_BASELINE.md">Runtime baseline</a>
  ·
  <a href="docs/V12_CONTROLLED_DEPLOY_CONTRACT.md">Controlled deploy</a>
  ·
  <a href="https://github.com/rozkalnsandris/RPi5_main/actions">Actions</a>
</p>

<p align="center">
  <a href="https://github.com/rozkalnsandris/RPi5_main/actions/workflows/validate.yml">
    <img src="https://github.com/rozkalnsandris/RPi5_main/actions/workflows/validate.yml/badge.svg?branch=main" alt="RPi5 Main validation status">
  </a>
</p>

RPi5 Main is the infrastructure source of truth for the Raspberry Pi 5 host.
Configuration is imported incrementally and becomes authoritative only after a
reviewed change path. Secrets, private keys, credentials, runtime data, database
data, Docker volumes, and backups are never stored in Git.

| | |
|---|---|
| **Role** | host infrastructure · runtime ownership · controlled operations |
| **Host** | Raspberry Pi 5 · Debian · Docker/systemd services |
| **Workflow** | branch · tests · Draft PR · CI · review · squash merge |
| **Safety** | exact commit binding · least privilege · preflight · rollback · no secrets in Git |

## Change workflow

Every change follows: **branch → tests → draft PR → CI → review → squash merge**.

Any production apply must bind to an exact Git commit and include preflight checks, a backup plan, verification, and a documented rollback. A merge never deploys automatically.

## Controlled deploy

V12 adds a VS Code-friendly operator workflow for the exact non-secret V10 backup implementation files already owned by this repository:

- **RPi5: Sync from GitHub**
- **RPi5: Test**
- **RPi5: Install deploy engine**
- **RPi5: Deploy engine status**
- **RPi5: Deploy plan**
- **RPi5: Deploy reviewed plan**
- **RPi5: Status**
- **RPi5: Rollback latest**
- **RPi5: Deploy logs**

The repository controller runs as the normal operator. Privileged commands are routed to a separately confirmed, versioned and root-owned engine below `/usr/local/libexec/rpi5-deploy/releases/<commit>/`. The root wrapper starts with a clean environment and fixed `PATH`. Every root action verifies the installed engine files; plan, deploy and status also require the current tracked controller, modules and manifest to match the hashes recorded during engine installation. Rollback and logs remain available from the verified engine and transaction state during repository-source drift.

Plan and deploy are deliberately separate. The root-owned plan is short-lived and binds the exact commit, successful GitHub checks, host health, backup freshness, reviewed runtime baseline, source hashes and complete live/desired SHA-256, UID, GID and mode fingerprints. Apply uses private transaction backups, fsync, same-directory replacement, post-write validation and automatic rollback.

V12 does not deploy the private `/etc/rpi5-backup.conf`, restart or reload services, run a backup, upload data, delete retention data, rotate logs or change production merely by being merged. Engine installation and any later target apply are separate explicit actions after merge.

## Versions

V01 is inventory-only. Its collector is read-only, creates a bounded and sanitized local evidence bundle, and makes no production changes. Generated evidence remains ignored and untracked.

V02A is complete. It adds a least-privilege, read-only diagnostic that compares approved execution contexts without granting access or changing the host.

V02B is complete. It records a verified, sanitized runtime baseline from the approved host-equivalent read-only context. The tracked baseline is bound to ignored, checksummed evidence and is not deployment configuration.

V03 is complete. It compares two sanitized V02B JSON baselines offline and deterministically; it performs no host collection, monitoring, alerting, deployment, or remediation.

V04 is complete as tooling. It adds an offline, human-gated review, decision, archive, and accepted-only promotion workflow.

V05 is complete. It performed the first real temporal runtime refresh through V02B collection, V03 diff review, an explicit accepted V04 decision, archival of the previous baseline, and promotion of the exact reviewed candidate.

V06 is complete. It adds backward-compatible v2 runtime-diff semantics that retain exact dynamic socket and `veth` observations while grouping stable-profile churn for review.

V07 is complete. It verifies that every accepted archive transition forms one continuous, acyclic lineage ending at the exact tracked current baseline and Markdown projection.

V08 tooling is complete. It adds a bounded, non-root memory-pressure diagnostic for issue #5; a real RPi5 evidence collection remains a separate post-merge action.

V09 is complete. It analyzes chronological verified V08 bundles offline, normalizes memory units to KiB, renders correct MiB trends and distinguishes isolated activity from sustained pressure.

V10 imports byte-identical source ownership for the existing host-wide encrypted backup implementation from Hermes Tech. It pins source blobs and SHA256 values, documents installed mappings and rollback, and performs no production verification or deployment.

V11 tooling is complete. It attributes the exact AdGuard Home process and container memory to anonymous, file-backed, shared, kernel/socket, slab, and swap classes without reading DNS queries, client data, process arguments, environments, or raw configuration.

V12 adds the root-isolated, human-reviewed, exact-commit deployment engine and transaction workflow for only the three approved non-secret V10 installed files. Production engine installation and target deployment remain separate explicit actions after merge.

V13 establishes host-wide ownership for the shared Cloudflare Tunnel connector. The tunnel remains remotely managed in Cloudflare; this repository reviews the exact host `cloudflared` systemd source, secret boundary, edge-readiness gates and no-downtime migration/rollback contract. Merging V13 does not install, start, stop or restart the connector and does not change Cloudflare routes, UFW or application origins.

V14 adds reviewed host ownership for the Hermes Tech static web container and its loopback-only `127.0.0.1:8089` origin. The source pins the exact retained production image ID, forbids an implicit Nginx update, makes systemd the only restart supervisor, and defines a separately confirmed route/container/UFW migration with rollback. Merging V14 performs no production mutation.

See [the roadmap](docs/ROADMAP.md), [the security model](docs/SECURITY_MODEL.md), [the V01 inventory contract](docs/INVENTORY_CONTRACT.md), [the V02A findings](docs/V02A_FINDINGS.md), [the current runtime baseline](docs/CURRENT_RUNTIME_BASELINE.md), [the V04 review contract](docs/V04_BASELINE_REVIEW_CONTRACT.md), [the V05 findings](docs/V05_FINDINGS.md), [the V06 semantics contract](docs/V06_DYNAMIC_RUNTIME_SEMANTICS.md), [the V07 lineage contract](docs/V07_RUNTIME_LINEAGE_CONTRACT.md), [the V08 memory diagnostic contract](docs/V08_MEMORY_PRESSURE_DIAGNOSTIC_CONTRACT.md), [the V09 memory series contract](docs/V09_MEMORY_PRESSURE_SERIES_CONTRACT.md), [the V10 backup ownership contract](docs/V10_BACKUP_OWNERSHIP_CONTRACT.md), [the V11 AdGuard memory attribution contract](docs/V11_ADGUARD_MEMORY_ATTRIBUTION_CONTRACT.md), [the V12 controlled deploy contract](docs/V12_CONTROLLED_DEPLOY_CONTRACT.md), [the V13 Cloudflare Tunnel ownership contract](docs/V13_CLOUDFLARE_TUNNEL_OWNERSHIP_CONTRACT.md), and [the V14 Hermes Tech web runtime contract](docs/V14_HERMES_TECH_WEB_RUNTIME_CONTRACT.md).
