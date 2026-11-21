# Hermes Deals Sunday image retention v1 — source-only proposal

**Status: SOURCE ONLY.** On 2026-11-21 the owner approved automatic Sunday Hermes image cleanup alongside weekly maintenance. This source does **not** authorize installation, timer activation, Docker deletion, service restart or a manual run. Merge is not LIVE authorization.

## Owner boundary and schedule

- The RPi5-maintenance updater remains **unchanged**: it owns main Compose updates and conservative dangling-image pruning only. No global prune -a or cross-project mutation is added.
- RPi5_main owns a **separate Hermes-only service/timer**. It is scheduled for **Sunday 04:30 Europe/Berlin**, after the updater's Sunday 02:20 window and 2-hour timeout. Persistent=false prevents after-reboot catch-up deletion.
- Before mutation the executor verifies rpi5-update.service Result=success, ExecMainStatus=0, and a **same-Sunday 02:20–current-time exit timestamp**. Its deletion window is 04:00–05:59. If the updater failed, is still active, or reboot erased its status, deletion stops.
- It uses the already existing root-owned shared /run/lock/rpi5-maintenance-exclusive.lock. Busy/unsafe lock means STOP, never bypass. It does not start Docker, the updater or SIMPLE-DEPLOY.
- Ordinary SIMPLE-DEPLOY reconciliation continues to forbid destructive cleanup. This is an independent app-owned operation.

## Exact deletion envelope

Only local image IDs with exactly one tag and one digest equal to ghcr.io/rozkalnsandris/hermes-deals@sha256:<full-image-ID> may qualify. This is the unusual digest-only local representation observed on rpi5; unrelated images or additional tags never qualify.

1. Require host rpi5, root account, correct root-only state and shared lock, and Hermes loopback HTTP 200 at http://127.0.0.1:9128/api/health.
2. Both protected historical image IDs must still be inspectable:
   - sha256:03c16c206ab28711a0ae9c34f30321570340a07d430e332166945dc640e94243 (verified production baseline);
   - sha256:69d865fc8becf18395ed7bb38d4a62ff6f0b057033bc3bd5747858f7c410d55c (verified rollback baseline).
3. Never delete an image referenced by **any running or stopped container**. Require a creation timestamp at least **14 × 24 hours** old and a 40-hex OCI source revision. Unknown provenance or other tag/digest sets are excluded.
4. Select the **32 oldest qualifying images at most**, revalidate exact identity and container state before every deletion, remove through docker image rm --no-prune with the one exact image reference. No --force, prune, volume, container, package/network/config change, restart or reboot.
5. Post-verification requires exactly the selected image-ID delta, unchanged containers/running state/volume names, both protected images still present, and healthy Hermes HTTP response.

The static protected IDs are reviewed baseline **safety pins**, not proof of the latest rollback. Future changes to the owner-selected rollback require reviewed source updates and a separate exact LIVE installation. If either pin disappears, the executor stops, not deletes.

## Sticky STOP and receipts

Before the first Docker removal, the executor writes a fsynced and atomic root-private state.json with state=BLOCKED and the SHA256 of the comma-joined selected image IDs. If a call fails, times out, process crashes or post-verification detects drift, this marker remains and **all later unattended runs stay blocked**. Only complete success writes state=DONE. No retry, rollback, automatic marker removal or alternate mutation path.

Logs include bounded PREFLIGHT, removed image IDs, DONE/STOP only; never print secrets, image environments, raw config or application data. Read-only --check remains a protected host-local operation; manual --apply is prohibited without separate exact LIVE authorization.

## Future activation gate — NOT YET AUTHORIZED

Before any LIVE changes: pin the reviewed merged RPi5_main SHA and the source blobs, verify the current rpi5 running/rollback image IDs, all container references, lock, same-weekly update evidence, protected file metadata and Hermes health.

A separate owner-approved LIVE plan may install precisely:

- ops/lib/deploy_executor/hermes_image_retention_v1.py into /usr/local/libexec/rozkalns-hermes-image-retention/hermes_image_retention_v1.py;
- ops/systemd/rozkalns-hermes-image-retention.service and .timer into /etc/systemd/system;
- only the necessary daemon-reload and this one timer enable/start, with read-only verification; **no manual cleanup run**.

A failed or ambiguous installation/activation after the first mutation is STOP with no retry or rollback. The first eligible scheduled cleanup is only after actual approved activation and a successful Sunday update. Source-only checks cannot prove live results.

References: [RPi5-maintenance #15](https://github.com/rozkalnsandris/RPi5-maintenance/issues/15), [maintenance runbook](https://github.com/rozkalnsandris/RPi5-maintenance/blob/main/docs/OPERATIONS_RUNBOOK.md), [SIMPLE-DEPLOY host contract](SIMPLE_DEPLOY_HOST_V1.md), [Docker image prune](https://docs.docker.com/reference/cli/docker/image/prune/).

## Source tests

Run python3 tests/test-hermes-image-retention-v1.py; the test uses only synthetic Docker inputs and temporary state. CI executes it in the deploy-control regression group.
