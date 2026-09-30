# SIMPLE-DEPLOY v1 trusted host contract

Issue: `#666`  
Hermes compatibility prerequisite: `#690`  
Hermes static source target registration: `#692`

Status: **Weather is the activated standing SIMPLE-DEPLOY target. Hermes Deals is the second reviewed source target, but it is not installed or activated on the RPi5 and still requires a separate exact LIVE/cutover gate.**

Historical evidence below retains the phrases `Phase A install-only completed` and `Phase B is stopped pre-mutation` where needed to document resolved Weather checkpoints and preserve validator compatibility.

This repository owns the trusted RPi5/runtime half of SIMPLE-DEPLOY v1. The accepted GitHub-side contract is `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`. Source merge here does not install, enable, start, restart or mutate the live RPi5.

## Ownership boundary

`ops-workflows` builds and publishes consumer images on GitHub-hosted runners. It advances `<image>:production` only as a discovery pointer and records immutable GHCR digest plus source/shared-workflow identity.

`RPi5_main` owns one generic pull reconciler. Consumers do not supply shell, argv, host paths, Compose paths, repository names, service names or environment values at runtime. Every mutation-capable value comes from the tracked, reviewed static RPi5 target registry.

The generic executor remains `ops/lib/deploy_executor/simple_deploy_v1.py`; adding Hermes does not add project-directory, env-file, host-path, environment, credential, argv or command authority.

## Source artifacts

- `ops/lib/deploy_executor/simple_deploy_v1.py` — strict parser, discovery, reconciliation, health verification, receipt and fail-closed state machine.
- `ops/bin/rozkalns-simple-deployer` — fixed CLI exposing only `--all` or one reviewed `--target` alias.
- `ops/deploy/simple-deploy-targets-v1.json` — tracked static target registry.
- `ops/deploy/simple-deploy-compose/rozkalns-weather-public.yml` — exact reviewed Weather Compose source, hash-pinned by the registry.
- `ops/deploy/simple-deploy-compose/hermes-deals-api.yml` — RPi5-owned Hermes API-only adapter, hash-pinned by the registry.
- `ops/contracts/simple-deploy-hermes-compat-v1.json` — Hermes no-secrets/dependency-isolation compatibility contract.
- `ops/contracts/simple-deploy-host-v1.json` — machine-readable host/trust-boundary contract.
- `ops/systemd/rozkalns-simple-deployer.service` and `.timer` — reviewed standing reconciliation units; only the already-activated Weather target is currently proven live through this path.
- `tests/test-simple-deploy-v1.py` and `tests/test-simple-deploy-hermes-compat-v1.py` — tracked-target, adversarial and compatibility tests.
- `ops/sysusers/rozkalns-simple-deployer.conf` — declarative static runtime principal plus explicit `docker` supplementary-group membership.
- `scripts/install-simple-deploy-v1.py` + `ops/deploy/simple-deploy-installer-v1.json` — exact-SHA first-install source. The installer does not reload systemd, start/enable the timer, run Docker or reconcile a target.

The tracked registry has `execution_enabled: true` and two reviewed source targets: `rozkalns-weather-public-rpi5` and `hermes-deals`. Only Weather has completed the one-time host activation. Target adoption remains a tracked source review, never a runtime parameter; source registration alone does not install a target on the host.

## Weather canary binding — activated standing target

The Weather target is derived from the accepted consumer contract at `rozkalnsandris/rozkalns_weather@606981d10eee59d13b802f6a682abf1daa2aa8a5`:

- image: `ghcr.io/rozkalnsandris/rozkalns_weather`;
- target alias: `rozkalns-weather-public-rpi5`;
- architecture: `linux/arm64`;
- Compose project/service: `rozkalns-weather-public` / `weather`;
- Compose file: `rozkalns-weather-public.yml`;
- Compose SHA-256: `80e2b47e4ed039c38285094e0b273fbc884f0a34ff34d8b201d8e93323af1f32`;
- loopback liveness/readiness: `http://127.0.0.1:9180/health` / `http://127.0.0.1:9180/ready`;
- persistent volume: `weather_data`;
- registry profile: `public-anonymous-pull`;
- bounded Compose wait timeout: 180 seconds.

Weather's one-time Phase A/B/C activation is completed historical evidence. Its standing ordinary `AUTO_DEPLOY_SAFE` release path is active for this fixed target only.

## Hermes Deals binding — source registered, not installed

The first non-Weather reuse target is frozen against accepted consumer revision `rozkalnsandris/hermes-deals@13f9fb69b9576d8e97ab3a85334927f3c576ca1c` and compatibility prerequisite #690:

- image: `ghcr.io/rozkalnsandris/hermes-deals`;
- target alias: `hermes-deals`;
- architecture: `linux/arm64`;
- accepted shared workflow: `e05ed760791a127c7c9628696806ef39c9fe329c`;
- Compose project/service: `hermes-deals` / `api`;
- Compose file: `hermes-deals-api.yml`;
- Compose SHA-256: `644dc72da5dc13ee532dd29693db31358451669bb44de4df4b62c41736903f1c`;
- loopback liveness: `http://127.0.0.1:9128/api/health` through the existing Hermes web proxy;
- readiness: explicitly `not-applicable`;
- persistent database-volume identity: `hermes_deals_pgdata`;
- registry profile: `public-anonymous-pull`;
- bounded Compose wait timeout: 180 seconds.

The adapter intentionally defines only `api`, joins the existing external `hermes-deals_internal` network and contains no `db`, `web`, `worker`, `depends_on`, local build or `--remove-orphans` behavior. Ordinary reconciliation therefore cannot use a Compose dependency graph to recreate or restart those unrelated services.

The adapter fixes private runtime configuration lookup at `/etc/rozkalns-simple-deployer/private/hermes-deals-api.env` without committing its values, and fixes bind identities under `/var/lib/rozkalns-simple-deployer/hermes-deals/...` with `create_host_path: false`. Source issue #692 does not create those paths, provision that file, install the source registry under `/etc`, run Docker or reconcile Hermes.

`hermes_deals_pgdata` is an application persistence invariant only. Ordinary SIMPLE-DEPLOY must not create, migrate, initialize, restore, backfill, delete or clean database/schema/data state.

## Immutable desired state

For each installed and statically allowlisted target the reconciler:

1. verifies the root-owned installed registry/identity and hash-pinned Compose file;
2. anonymously resolves only `<allowlisted-image>:production` for an eligible public image;
3. freezes the returned `sha256:...` digest for the attempt;
4. verifies ARM64 image metadata plus consumer source SHA, target alias and allowlisted shared-workflow SHA labels;
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

A target binds exactly: alias, consumer repository/image, `linux/arm64`, accepted shared workflow SHA, Compose project/file/file SHA-256/service, loopback liveness/readiness URLs, bounded wait timeout, receipt name, persistent-volume identities, registry pull profile and the complete fixed forbidden-operation list.

Unknown fields fail closed. Compose file names cannot contain directories. Health URLs must be explicit `http://127.0.0.1:<port>/<path>` values with no credentials, query or fragment. The image must be exactly the GHCR image derived from the consumer repository.

`public-anonymous-pull` is the active reviewed profile for both source targets. `private-read-only` remains schema-reserved and fails before mutation until a separate reviewed credential/auth contract exists.

## Mutation and failure semantics

The first `docker compose pull` is treated as the start of live mutation. From that point onward, command failure, timeout/transport failure, Compose failure, container identity mismatch, liveness/readiness regression or other ambiguity writes a minimal `STOP_ERROR` status and blocks later automatic attempts for that target.

There is no automatic rollback, cleanup, alternate image/tag or retry loop. Persistent volumes are never removed, recreated, migrated, restored or backfilled by this ordinary path. The implementation contains no Compose `down`, volume removal, database/data operation, package change, unrelated systemd mutation, Cloudflare/network change or secret/permission change.

Mutation-capable work is serialized per target by a non-blocking lock. A blocked target remains blocked until a future separately reviewed recovery contract defines what may clear or recover it.

## One-time activation gate — Weather completed, Hermes still pending

Source readiness is not LIVE authority.

Weather required separate exact LIVE authorization for each reviewed mutation phase, and those one-shot authorities are consumed/non-reusable. Accepted Weather completion evidence binds the activated target to the reviewed registry/Compose/principal contract and preserved `weather_data` volume.

Hermes source registration does not inherit that Weather authority. A future Hermes cutover must separately bind the exact then-current `RPi5_main` SHA, static target `hermes-deals`, reviewed adapter hash, host-owned bind namespace, private runtime-config identity and exact release/digest evidence before the first host mutation.

That later gate may cover only reviewed target materialization and bounded first reconciliation/E2E verification. It does not imply database/schema/data migration, destructive recovery, Cloudflare/network changes, settings/secrets/permissions changes or unrelated host control.

## Current sequence

`ops-workflows#97` is merged at `e05ed760791a127c7c9628696806ef39c9fe329c`; Weather has completed its one-time cutover, standing release proof and public runtime/UI acceptance; Hermes compatibility prerequisite #690 is merged; and #692 is the first non-Weather static source target-adoption outcome.

The sequence from here is:

```text
Weather shared SIMPLE-DEPLOY canary + standing release proof — COMPLETE
-> Weather public-data/runtime/UI acceptance — COMPLETE
-> Hermes compatibility prerequisite #690/#691 — COMPLETE
-> Hermes static source target binding #692 — CURRENT SOURCE OUTCOME
-> exact-main verification after source merge
-> separate exact Hermes host materialization/cutover + first reconciliation/E2E gate
-> prove at least one additional non-Weather reuse before declaring SIMPLE-DEPLOY stable/default
-> only then reconsider ops-workflows#96 Queue vNext
```

Do not revive the older Hermes project-specific Phase-4/control-plane deployment path as an alternative ordinary application-release framework.

## Weather canary first-activation sequencing (#674) — historical/completed

Fresh #669 preflight originally proved that Weather could not safely run the first ordinary reconciliation while production schema was absent. The one-time sequence was therefore frozen as **install-only -> separately authorized schema init -> readiness 200 -> activation/reconciliation**.

Compatibility marker retained: **Phase A install-only completed**.

The schema-init companion remains outside ordinary SIMPLE-DEPLOY. Its accepted one-time execution preserved the existing Weather data volume, did not backfill corpus or activate ingest, and produced `/ready=200`. Its completed one-shot authorization is not reusable.

Historical first-install authority boundary retained for contract compatibility: #672 was the source-only principal/installer prerequisite and does not silently widen #669. At that checkpoint, the rule was that #669 must be freshly reconciled after #672 merged before any separately authorized installer/LIVE apply. That rule was satisfied by the later exact owner-gated Phase A/B/C sequence; it is retained here as history, not as a current pending gate.

## Phase-B post-install execution/state correction (#674 follow-up) — historical/completed

Compatibility marker retained: **Phase B is stopped pre-mutation** described an earlier resolved checkpoint after `IMAGE_CONTRACT_FAILED` / `POINTER_RESOLUTION_FAILED`.

The later **Phase-B post-install execution/state correction** reconciled only the reviewed helper/source identity/runtime-owned state paths under its separate exact LIVE authorization. It did not create standing permission for future repairs.

These historical sections preserve why the split gates existed; they do not reopen consumed authority or replace fresh current-state checks.
