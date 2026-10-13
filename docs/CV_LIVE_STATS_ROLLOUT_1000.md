# CV-only live-stats rollout (#1000)

**SOURCE-ONLY. No merge or LIVE authority.** The fixed operator
`ops/bin/rozkalns-cv-live-stats-rollout-1000` is not installed by source delivery.

## Immutable target contract

The consumer is `rozkalns-cv@5055f596e219eee5ff893b4a08af51e871e99e6f`
at immutable digest
`sha256:44904ef38cdbcaa5a0634a8d3d08ba70ce047d97ee84c947c068eab75d1f5944`.
The already healthy CV image returns HTTP 404 for /stats.json because the
installed Compose adapter lacks the read-only host statistics directory mount.

Installed registry SHA-256:
`91a2fe2d86d9da9ac4ee7a5031eea7a405d3d42faec24ed089b08534c7ac0f23`.
Installed CV Compose SHA-256:
`d4c7e9ed5c36245d92ce7da199194ec032c74de6ea03f2b522e31a43ffaf3277`.
Desired CV Compose SHA-256:
`6f14d9cbe07b2c03c4e9e14172de4318c1e8d591b97dd595dd82aacb38b7f19c`.

The operator derives the new installed registry by substituting only the
single CV Compose SHA token in the historical baseline registry. Every other
target and byte, including Hermes, remains untouched. Installing the current
repository's complete registry is **outside** this operation.

## Future exact Composite LIVE decision — not granted

A separate owner authorization must approve the fixed operator installation
at `/usr/local/sbin/rozkalns-cv-live-stats-rollout-1000` (root-owned, mode 0500);
reviewed candidate Compose staging at `/usr/local/share/rozkalns-cv-stats-1000.yml`
(root-owned, mode 0444); and a separate root-owned, mode 0400 approval artifact
at `/run/rozkalns-cv-stats-1000-approval.json`. The approval JSON must match
exactly the schema, pins and operator hash in `owner_approval()`. None of
those host writes is authorized by merge.

CHECK resolves a unique producer snapshot under a passwd-discovered home using
only fixed relative directory/file metadata; it rejects unsafe, symlinked or
ambiguous paths and does not publish usernames or literal user-home paths.
It then uses strictly allowlisted metadata/hash reads of root-owned registry,
Compose candidate and current image override, systemd timer/service idle
status, restricted Docker digest/revision/mount metadata, and stats producer
file *metadata* (not its contents). It verifies healthy CV loopback readiness.
No .env, credentials, DB, application data, whole Docker environment, or logs
are read or printed. A stale producer, changed baseline, unsupported owner
state, wrong image digest, staging collision, symlink or concurrent drift
blocks before mutation.

The separately authorized APPLY stages and replaces just two fixed public
configuration files, then calls Docker Compose `up` for **only** the CV
service, with `--no-deps --force-recreate --pull never --no-build`, using
the existing verified same-digest override. It requires the exact read-only
mount, readiness HTTP 200, /stats.json HTTP 200 with JSON/no-store, and fresh
host producer metadata afterward. It does not manage timers, pull/build
images, alter DB/data, touch Cloudflare/DNS or restart unrelated services.

The **first staged write consumes LIVE authorization**. Any later failure
requires STOP without retry, rollback, cleanup or alternate mutation; partial
stages/configuration remain as evidence. A new owner decision is required for
recovery. Production readiness must not be inferred from passing source CI.

Synthetic tests: `python3 tests/test-cv-live-stats-rollout-1000.py`.
