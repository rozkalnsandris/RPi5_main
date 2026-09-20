# SIMPLE-DEPLOY v1 trusted host contract

Issue: `#666`

Status: **source contract only; inert and not installed**.

This repository owns the trusted RPi5/runtime half of SIMPLE-DEPLOY v1. The merged GitHub-side contract is `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`. Source merge here does not install, enable, start, restart or mutate the live RPi5.

## Ownership boundary

`ops-workflows` builds and publishes the consumer image on GitHub-hosted runners. It advances `<image>:production` only as a discovery pointer and records the immutable GHCR digest plus source/shared-workflow identity.

`RPi5_main` owns one generic pull reconciler. Consumers do not supply shell, argv, host paths, Compose paths, repository names, service names or environment values at runtime. Every mutation-capable value comes from the tracked, reviewed static RPi5 target registry.

Consumer repositories remain responsible only for their application contract. The first planned canary is `rozkalnsandris/rozkalns_weather#142`.

## Source artifacts

- `ops/lib/deploy_executor/simple_deploy_v1.py` — strict parser, discovery, reconciliation, health verification, receipt and fail-closed state machine.
- `ops/bin/rozkalns-simple-deployer` — fixed CLI exposing only `--all` or one reviewed `--target` alias.
- `ops/deploy/simple-deploy-targets-v1.json` — tracked static target registry.
- `ops/contracts/simple-deploy-host-v1.json` — machine-readable host/trust-boundary contract.
- `ops/systemd/rozkalns-simple-deployer.service` and `.timer` — future activation source, not installed by this change.
- `tests/test-simple-deploy-v1.py` — focused adversarial and reconciliation tests.

The tracked registry intentionally starts with `execution_enabled: false` and `targets: []`. Do not guess the Weather target identities before `rozkalns_weather#142` fixes its final Compose/service/health/persistence contract. Adding a target is a tracked source review, not a runtime parameter.

## Immutable desired state

For each statically allowlisted target the reconciler:

1. verifies the root-owned installed registry/identity and hash-pinned Compose file;
2. anonymously resolves only `<allowlisted-image>:production` for an eligible public image;
3. freezes the returned `sha256:...` digest for the attempt;
4. verifies ARM64 image metadata plus the consumer source SHA, target alias and allowlisted shared-workflow SHA labels;
5. compares the frozen digest with the last successful receipt;
6. no-ops when already current;
7. otherwise writes a local Compose override containing only `<allowlisted-image>@<frozen-digest>`;
8. runs only the fixed Compose pull/up/wait lifecycle for the allowlisted service;
9. verifies the running container still names the frozen digest reference;
10. checks fixed loopback liveness and, when required, readiness;
11. re-reads the production pointer only as evidence; a newer digest waits for the next reconciliation;
12. persists the exact successful digest/source/shared revision receipt.

The mutable `production` tag is never the deployment identity.

## Static target contract

A target binds exactly: alias, consumer repository/image, `linux/arm64`, accepted shared workflow SHA, Compose project/file/file SHA-256/service, loopback liveness/readiness URLs, bounded wait timeout, receipt name, persistent volume identities, registry pull profile and the complete fixed forbidden-operation list.

Unknown fields fail closed. Compose file names cannot contain directories. Health URLs must be explicit `http://127.0.0.1:<port>/<path>` values with no credentials, query or fragment. The image must be exactly the GHCR image derived from the consumer repository.

`public-anonymous-pull` is the only active v1 pull profile. `private-read-only` is schema-reserved but fails before mutation until a separate reviewed credential/auth contract exists.

## Mutation and failure semantics

The first `docker compose pull` is treated as the start of live mutation. From that point onward, command failure, timeout/transport failure, Compose failure, container identity mismatch, liveness/readiness regression or other ambiguity writes a minimal `STOP_ERROR` status and blocks later automatic attempts for that target.

There is no automatic rollback, cleanup, alternate image/tag or retry loop. Persistent volumes are never removed, recreated, migrated, restored or backfilled by this ordinary path. The implementation contains no Compose `down`, volume removal, database/data operation, package change, unrelated systemd mutation, Cloudflare/network change or secret/permission change.

Mutation-capable work is serialized per target by a non-blocking lock. A blocked target remains blocked until a future separately reviewed recovery contract defines what may clear or recover it.

## One-time activation gate

After this source is merged and the first consumer contract is ready, activation still requires a separate exact LIVE authorization. That authorization must bind the host `rpi5`, exact merged `RPi5_main` SHA, exact deployer/module/unit/timer artifacts, exact initial tracked target registry and Compose files, runtime baseline, installation/enable mutations, verification and any explicitly reviewed rollback semantics.

The cutover must materialize an identity file with schema `rozkalns.rpi5-main.simple-deploy.identity.v1`, repository `rozkalnsandris/RPi5_main` and the exact activated source SHA. It must install the reviewed registry and Compose files as root-owned, non-group/world-writable regular files. No target may be invented or widened during the live gate.

After a successful cutover, ordinary `AUTO_DEPLOY_SAFE` releases for already-adopted targets may reconcile without a fresh per-release LIVE decision. Database/data, destructive recovery, secrets/permissions, Cloudflare/network, private-provider activation and unrelated host-control classes remain separate exact gates.

## Current sequence

`ops-workflows#97` is merged at `e05ed760791a127c7c9628696806ef39c9fe329c`. This #666 source contract is next. Then Weather #142 fixes the first consumer identities. Only after both source sides are ready may the one-time Weather/RPi5 LIVE cutover be proposed.
