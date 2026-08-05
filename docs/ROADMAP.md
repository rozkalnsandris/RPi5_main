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

## Later phases

Each subsystem is imported separately with redaction, tests, rollback instructions and a pull request.
