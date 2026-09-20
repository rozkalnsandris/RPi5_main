# SIMPLE-DEPLOY v1 trusted host contract

Issue: `#666`

Status: **Phase A install-only completed at `b57ed42d5eb01f15b62c1f53459ffe0539a57d9c`; Phase B is stopped pre-mutation pending the reviewed execution-identity/Docker-state source correction.** Fresh GitHub/#191 state must be re-read before any consequential continuation.

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
- `ops/systemd/rozkalns-simple-deployer.service` and `.timer` — future activation source, not installed by this change.
- `tests/test-simple-deploy-v1.py` — focused adversarial, reconciliation and tracked-target tests.
- `ops/sysusers/rozkalns-simple-deployer.conf` — declarative static runtime principal plus explicit `docker` supplementary-group membership.
- `scripts/install-simple-deploy-v1.py` + `ops/deploy/simple-deploy-installer-v1.json` — exact-SHA, first-install-only, fail-closed installer source. The installer does not reload systemd, start/enable the timer, run Docker or reconcile a target.

The tracked registry now has `execution_enabled: true` and exactly one reviewed target, `rozkalns-weather-public-rpi5`. This is source readiness only: nothing reads this repository file on the production host until a separate LIVE cutover installs the exact reviewed registry, Compose file, deployer identity and units. Target adoption remains a tracked source review, never a runtime parameter.

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

`public-anonymous-pull` is the only active v1 pull profile. `private-read-only` is schema-reserved but fails before mutation until a separate reviewed credential/auth contract exists. The one-time cutover must freshly prove anonymous pull; package visibility/auth changes are not fallback authority.

## Mutation and failure semantics

The first `docker compose pull` is treated as the start of live mutation. From that point onward, command failure, timeout/transport failure, Compose failure, container identity mismatch, liveness/readiness regression or other ambiguity writes a minimal `STOP_ERROR` status and blocks later automatic attempts for that target.

There is no automatic rollback, cleanup, alternate image/tag or retry loop. Persistent volumes are never removed, recreated, migrated, restored or backfilled by this ordinary path. The implementation contains no Compose `down`, volume removal, database/data operation, package change, unrelated systemd mutation, Cloudflare/network change or secret/permission change.

Mutation-capable work is serialized per target by a non-blocking lock. A blocked target remains blocked until a future separately reviewed recovery contract defines what may clear or recover it.

## One-time activation gate

Source readiness is not LIVE authority. Activation still requires a separate exact LIVE authorization binding host `rpi5`, the exact merged `RPi5_main` SHA, deployer/module/unit/timer artifacts, the exact tracked registry and Weather Compose bytes, a minimum-sufficient runtime baseline, installation/enable mutations, verification and any explicitly reviewed rollback semantics.

The cutover must materialize an identity file with schema `rozkalns.rpi5-main.simple-deploy.identity.v1`, repository `rozkalnsandris/RPi5_main` and the exact activated source SHA. It must install the reviewed registry and Compose files as root-owned, non-group/world-writable regular files. No target may be invented, edited or widened during the live gate.

The first-install prerequisite is source-controlled by #672. The reviewed installer accepts one exact expected `RPi5_main` SHA, requires that exact clean checkout and origin, verifies every install target is absent before the first mutation, installs only fixed reviewed bytes, and provisions the static `rozkalns-simple-deployer` user/group through the tracked `sysusers.d` declaration. The declaration also makes the account a member of the already-existing `docker` group required by the unit. This user/group plus Docker-group membership change is a LIVE permission boundary; source merge does not authorize or execute it. `StateDirectory=rozkalns-simple-deployer` keeps `/var/lib/rozkalns-simple-deployer` ownership systemd-managed when the service is later started.

The installer stops at `SIMPLE_DEPLOY_INSTALLED_NOT_ACTIVATED`: it does **not** call `systemctl daemon-reload`, enable/start the timer or service, pull an image, run Compose or reconcile Weather. Those activation operations remain a later exact LIVE envelope. If any privileged installer mutation has started and a later installer step fails, there is no automatic retry, cleanup or rollback.

The current #669 issue text predates discovery of the missing runtime principal and explicitly excludes user/group/permission mutation. #672 does not silently widen #669. After this source prerequisite is merged and exact-main CI is green, #669 must be freshly reconciled and the owner LIVE authorization must explicitly include the reviewed principal provisioning before any installer apply.

After a successful cutover, ordinary `AUTO_DEPLOY_SAFE` releases for already-adopted targets may reconcile without a fresh per-release LIVE decision. Database/data, destructive recovery, secrets/permissions, Cloudflare/network, private-provider activation and unrelated host-control classes remain separate exact gates.

## Current sequence

`ops-workflows#97` is merged at `e05ed760791a127c7c9628696806ef39c9fe329c`; the generic RPi5 executor is merged; Weather #142 is merged at `606981d10eee59d13b802f6a682abf1daa2aa8a5`; and the first static Weather target is tracked. The first #669 read-only host preflight then proved that the unit-required `rozkalns-simple-deployer` principal was absent and no reviewed provisioning path existed. #672 is the source-only prerequisite that closes that gap. Only after #672 is merged/revalidated and #669 is freshly reconciled may a one-time Weather/RPi5 LIVE cutover authorization be requested.
## Weather canary first-activation sequencing (#674)

Fresh #669 preflight proved that Weather cannot safely run the first ordinary reconciliation while production schema is absent: the reviewed Compose healthcheck and generic reconciler both require `/ready=200`, while Weather intentionally uses `DATABASE_INIT_MODE=require-existing`.

The one-time canary sequence is therefore frozen as **install-only -> separately authorized schema init -> readiness 200 -> activation/reconciliation**. The #672/#674 first installer still performs no daemon-reload, service/timer start, Docker command, reconciliation or database/data mutation. It only installs the fixed `rozkalns-simple-deploy-weather-schema-init` companion source in addition to the generic deployer.

The companion is not part of ordinary SIMPLE-DEPLOY. A later exact data gate may invoke it with no caller arguments. It reuses the static Weather target, reviewed Compose hash and generic production-pointer/image-label validation, additionally requires the exact reviewed Weather consumer source `606981d10eee59d13b802f6a682abf1daa2aa8a5`, requires the existing `rozkalns-weather-public_weather_data` volume, freezes one immutable `image@sha256` reference, and runs only the reviewed `schema-init` service with that volume declared external. It never creates/deletes/recreates the volume, backfills corpus, activates ingest or starts the generic timer.

A PASS requires `/ready=200` and an unchanged production pointer after schema init. Any post-mutation error is STOP with no automatic retry, cleanup or rollback. Only after a PASS may #669 be freshly rebound to a separate activation gate for daemon-reload/timer enable/start and first bounded reconciliation. Source merge does not authorize any of those LIVE/data operations.

## Phase-B post-install execution/state correction (#674 follow-up)

The first Phase-B preflight after Phase A stopped before Docker/data mutation with `IMAGE_CONTRACT_FAILED` / `POINTER_RESOLUTION_FAILED`. The source defect was deterministic: the schema-init bridge forced `DOCKER_CONFIG=/etc/rozkalns-simple-deployer/docker-anonymous`, while that first-installer directory is intentionally `root:root 0755`. Docker Buildx uses client-side configuration/state under its Buildx configuration directory, so the non-root runtime principal cannot prove the registry/image contract through that path.

The corrected bridge freezes execution as `rozkalns-simple-deployer:rozkalns-simple-deployer` with the reviewed supplementary `docker` group and refuses root/other execution. It uses only `/var/lib/rozkalns-simple-deployer/docker-anonymous` for anonymous Docker client state and `/var/lib/rozkalns-simple-deployer/docker-anonymous/buildx` for Buildx state. Both parent directories must already be real `0700` directories owned by the fixed runtime principal; a Docker `config.json` is forbidden for the public-anonymous profile. The legacy root-owned `/etc/rozkalns-simple-deployer/docker-anonymous` directory is retained as inert Phase-A evidence and is no longer used by the bridge.

Because Phase A already installed the pre-correction helper bytes, source merge alone cannot repair the host. `scripts/install-simple-deploy-v1.py --phase-b-repair` is a one-shot, base-SHA-pinned post-install reconciliation mode. It accepts only the exact Phase-A base `b57ed42d5eb01f15b62c1f53459ffe0539a57d9c`, permits only the schema-init module plus generated source identity to change, and creates only the two runtime-owned state directories. It performs no `systemctl`, Docker, reconciliation or database/data action. Its apply path is a separate LIVE filesystem/identity gate; source merge does not authorize it.

After that repair PASS, the installed schema-init companion exposes exactly one non-mutating CLI mode, `--preflight`, in addition to the no-argument apply path. All other arguments remain forbidden. A successful `PRECHECK_READY` proves the fixed target/Compose/image labels, immutable digest, existing Weather volume, expected `/ready` state and absence of prior schema-init evidence before any schema/data authority is requested. The Phase-B data mutation and later Phase-C activation remain separate exact owner gates. There is no automatic retry, cleanup or rollback.
