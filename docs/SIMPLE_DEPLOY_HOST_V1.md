# SIMPLE-DEPLOY v1 trusted host contract

Issue: `#666`

Status: **Weather one-time SIMPLE-DEPLOY Phase A/B/C activation is complete on reviewed `RPi5_main@7c6c7a8a80ca62d783c7f378b5865fae348a3fe9`; the standing ordinary reconciliation timer is active for the fixed Weather target.** Fresh GitHub and minimum-sufficient runtime evidence must still be re-read before consequential continuation. Historical evidence below retains the earlier phrases `Phase A install-only completed` and `Phase B is stopped pre-mutation` only to document resolved checkpoints and preserve validator compatibility.

This repository owns the trusted RPi5/runtime half of SIMPLE-DEPLOY v1. The merged GitHub-side contract is `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`. Source merge here does not install, enable, start, restart or mutate the live RPi5.

## Ownership boundary

`ops-workflows` builds and publishes the consumer image on GitHub-hosted runners. It advances `<image>:production` only as a discovery pointer and records the immutable GHCR digest plus source/shared-workflow identity.

`RPi5_main` owns one generic pull reconciler. Consumers do not supply shell, argv, host paths, Compose paths, repository names, service names or environment values at runtime. Every mutation-capable value comes from the tracked, reviewed static RPi5 target registry.

Consumer repositories remain responsible only for their application contract. The first canary, `rozkalnsandris/rozkalns_weather#142`, is merged at `606981d10eee59d13b802f6a682abf1daa2aa8a5` and fixes the Weather target identities used below.

## Source artifacts

- `ops/lib/deploy_executor/simple_deploy_v1.py` — strict parser, discovery, reconciliation, health verification, receipt and fail-closed state machine.
- `ops/bin/rozkalns-simple-deployer` — fixed CLI exposing only `--all` or one reviewed `--target` alias.
- `ops/deploy/simple-deploy-targets-v1.json` — tracked static target registry.
- `ops/deploy/simple-deploy-compose/rozkalns-weather-public.yml` — exact reviewed Weather Compose source copied from the merged consumer revision and hash-pinned by the registry.
- `ops/contracts/simple-deploy-host-v1.json` — machine-readable host/trust-boundary contract.
- `ops/systemd/rozkalns-simple-deployer.service` and `.timer` — reviewed standing reconciliation units; the Weather one-time activation installed/activated their exact reviewed bytes under the separate Phase-C owner gate.
- `tests/test-simple-deploy-v1.py` — focused adversarial, reconciliation and tracked-target tests.
- `ops/sysusers/rozkalns-simple-deployer.conf` — declarative static runtime principal plus explicit `docker` supplementary-group membership.
- `scripts/install-simple-deploy-v1.py` + `ops/deploy/simple-deploy-installer-v1.json` — exact-SHA, first-install-only, fail-closed installer source. The installer does not reload systemd, start/enable the timer, run Docker or reconcile a target.

The tracked registry has `execution_enabled: true` and exactly one reviewed target, `rozkalns-weather-public-rpi5`. The completed one-time Weather cutover installed the exact reviewed registry, Compose file, deployer identity and units from `RPi5_main@7c6c7a8a80ca62d783c7f378b5865fae348a3fe9`. Target adoption remains a tracked source review, never a runtime parameter; this completion does not authorize adding or widening targets at runtime.

## Weather canary binding

The Weather target is derived from the merged consumer contract at `rozkalnsandris/rozkalns_weather@606981d10eee59d13b802f6a682abf1daa2aa8a5`:

- image: `ghcr.io/rozkalnsandris/rozkalns_weather`;
- target alias: `rozkalns-weather-public-rpi5`;
- architecture: `linux/arm64`;
- Compose project/service: `rozkalns-weather-public` / `weather`;
- installed Compose basename: `rozkalns-weather-public.yml`;
- Compose SHA-256: `80e2b47e4ed039c38285094e0b273fbc884f0a34ff34d8b201d8e93323af1f32`;
- loopback liveness/readiness: `http://127.0.0.1:9180/health` / `http://127.0.0.1:9180/ready`;
- persistent volume: `weather_data`;
- registry profile: `public-anonymous-pull`;
- bounded Compose wait timeout: 180 seconds.

The 180-second wait is bounded below the host-policy 300-second ceiling and covers the Weather Compose health window with margin. It does not authorize bootstrap, corpus/data work or any other profile service.

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

`public-anonymous-pull` is the only active v1 pull profile. `private-read-only` is schema-reserved but fails before mutation until a separate reviewed credential/auth contract exists. The completed Weather cutover proved anonymous public-image resolution for the accepted canary; package visibility/auth changes remain outside fallback authority.

## Mutation and failure semantics

The first `docker compose pull` is treated as the start of live mutation. From that point onward, command failure, timeout/transport failure, Compose failure, container identity mismatch, liveness/readiness regression or other ambiguity writes a minimal `STOP_ERROR` status and blocks later automatic attempts for that target.

There is no automatic rollback, cleanup, alternate image/tag or retry loop. Persistent volumes are never removed, recreated, migrated, restored or backfilled by this ordinary path. The implementation contains no Compose `down`, volume removal, database/data operation, package change, unrelated systemd mutation, Cloudflare/network change or secret/permission change.

Mutation-capable work is serialized per target by a non-blocking lock. A blocked target remains blocked until a future separately reviewed recovery contract defines what may clear or recover it.

## One-time activation gate — completed Weather canary

Source readiness is not LIVE authority. The Weather canary therefore required a separate exact LIVE authorization for each reviewed mutation phase, and all such one-shot authorities are now consumed/non-reusable.

Accepted completion evidence binds the activated source to `RPi5_main@7c6c7a8a80ca62d783c7f378b5865fae348a3fe9`, the fixed target `rozkalns-weather-public-rpi5`, Weather source `606981d10eee59d13b802f6a682abf1daa2aa8a5`, shared workflow `e05ed760791a127c7c9628696806ef39c9fe329c`, Compose SHA-256 `80e2b47e4ed039c38285094e0b273fbc884f0a34ff34d8b201d8e93323af1f32`, and the preserved `rozkalns-weather-public_weather_data` volume.

Phase A installed the reviewed artifacts/principal without activation. The post-install Phase-B repair then reconciled only the corrected schema helper/source identity/runtime-owned Docker-state directories. Phase B schema-init passed against the existing volume with `/ready` changing `503 -> 200`, no production-pointer change and frozen digest `sha256:d495d10b2d5e002a3c19b6532746624955269e0d483996c42ad6dea87e7afc38`. Phase C performed the first bounded ordinary reconciliation successfully for the same digest, verified `/health=200` and `/ready=200`, then enabled/started the reviewed timer. A later read-only check observed timer active/enabled, service result `success`/exit `0` and both endpoints still `200`.

After this successful cutover, ordinary `AUTO_DEPLOY_SAFE` releases for this already-adopted target may reconcile through the reviewed standing timer without a fresh per-release LIVE decision. Database/data work, destructive recovery, secrets/permissions, Cloudflare/network, private-provider activation, new target adoption and unrelated host-control classes remain separate exact gates.

## Current sequence

`ops-workflows#97` is merged at `e05ed760791a127c7c9628696806ef39c9fe329c`; Weather #142 is merged at `606981d10eee59d13b802f6a682abf1daa2aa8a5`; the generic RPi5 executor and static Weather target are merged; the Phase-B correction is merged at `RPi5_main@7c6c7a8a80ca62d783c7f378b5865fae348a3fe9`; and the one-time Weather Phase A/B/C runtime cutover is complete.

The next acceptance step is not another activation attempt. It is to prove one genuine newly merged eligible Weather release traverses the already-activated shared SIMPLE-DEPLOY path end to end and records exact consumer source/shared-workflow/image digest plus `/health=200` and `/ready=200`. Corpus/backfill/recurring-ingest and other sensitive data/host work remain separately gated.

## Weather canary first-activation sequencing (#674) — historical/completed

Fresh #669 preflight originally proved that Weather could not safely run the first ordinary reconciliation while production schema was absent: the reviewed Compose healthcheck and generic reconciler required `/ready=200`, while Weather intentionally used `DATABASE_INIT_MODE=require-existing`.

The one-time canary sequence was therefore frozen as **install-only -> separately authorized schema init -> readiness 200 -> activation/reconciliation**. That sequence is now complete. The installer itself still has the same normative non-activation contract: it performs no daemon-reload, service/timer start, Docker command, reconciliation or database/data mutation.

The schema-init companion remains outside ordinary SIMPLE-DEPLOY. Its accepted one-time execution preserved the existing `rozkalns-weather-public_weather_data` volume, used the reviewed immutable Weather image identity, did not backfill corpus or activate ingest, produced `/ready=200`, and observed no production-pointer change. Its completed one-shot authorization is not reusable.

## Phase-B post-install execution/state correction (#674 follow-up) — historical/completed

The earlier checkpoint was accurately described as `Phase B is stopped pre-mutation` after `IMAGE_CONTRACT_FAILED` / `POINTER_RESOLUTION_FAILED`. The source defect was deterministic: the schema-init bridge had forced Docker client state under root-owned `/etc` even though execution belonged to the non-root `rozkalns-simple-deployer` principal.

PR #676 corrected the bridge and merged as `RPi5_main@7c6c7a8a80ca62d783c7f378b5865fae348a3fe9`, freezing execution as `rozkalns-simple-deployer:rozkalns-simple-deployer`, preserving the reviewed supplementary `docker` group and moving anonymous Docker/Buildx state under runtime-owned `/var/lib/rozkalns-simple-deployer`.

Because Phase A had already installed pre-correction helper bytes, the separately authorized `--phase-b-repair` path reconciled only the schema-init module, generated source identity and two runtime-owned state directories. It performed no Docker, systemd activation, reconciliation or database/data operation. The subsequent `--preflight` returned `PRECHECK_READY`, the one-shot schema-init returned `PASS`, and Phase C later returned a successful first ordinary reconciliation before activating the standing timer.

These historical sections document why the split gates existed; they do not reopen any consumed authorization and do not replace fresh current-state checks.

Historical first-install authority boundary retained for contract compatibility: #672 was the source-only principal/installer prerequisite and does not silently widen #669. At that checkpoint, the rule was that #669 must be freshly reconciled after #672 merged before any separately authorized installer/LIVE apply. That rule was satisfied by the later exact owner-gated Phase A/B/C sequence; it is retained here as history, not as a current pending gate.
