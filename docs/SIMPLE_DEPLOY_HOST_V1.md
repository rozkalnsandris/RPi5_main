# SIMPLE-DEPLOY v1 trusted host contract

Issue: `#666`  
Hermes compatibility prerequisite: `#690`  
Hermes static source target registration: `#692`

Status: **Weather is the activated standing SIMPLE-DEPLOY target. Hermes Deals is the second reviewed source target, but it is not installed or activated on the RPi5 and still requires a separate exact LIVE/cutover gate.**

Historical evidence below retains the phrases `Phase A install-only completed` and `Phase B is stopped pre-mutation` where needed to document resolved Weather checkpoints and preserve validator compatibility.

This repository owns the trusted RPi5/runtime half of SIMPLE-DEPLOY v1. The original shared v1 baseline remains `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`; each tracked target is independently pinned by `shared_workflow_sha`. Weather now accepts `rozkalnsandris/ops-workflows@297f554519849ab8dcaadc5517e60b8269a6efaa` after the reviewed inline-cache-compatible shared update, while the other registered targets retain their existing pins. Source merge here does not install, enable, start, restart or mutate the live RPi5.

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

## Weather shared workflow pin alignment (#871)

The active Weather consumer moved its immutable reusable-workflow pin to `297f554519849ab8dcaadc5517e60b8269a6efaa`. The RPi5 target registry must match that exact image label or the trusted reconciler fails closed with `IMAGE_METADATA_INVALID` before runtime mutation.

This source change updates only the Weather target pin. Hermes Deals, Hermes Tech and CV remain on `e05ed760791a127c7c9628696806ef39c9fe329c`; Coloring Pages retains its separate reviewed pin. The whole-registry SHA-256 used by the existing Coloring Pages alignment source contract is updated mechanically because the tracked registry bytes changed.

Merge does **not** update `/etc/rozkalns-simple-deployer/targets.json`. Post-merge host alignment remains one separate exact LIVE filesystem mutation bound to the merged `RPi5_main` SHA and the fixed Weather target. The live preflight must revalidate the installed registry baseline and current healthy Weather runtime before replacement. No Docker/systemd restart, database/data change, network/Cloudflare change or secret access is required for this alignment. The timer may reconcile the already-published Weather candidate only after the installed registry matches the reviewed source.

## Weather canary binding — activated standing target

The Weather target is derived from the accepted consumer contract at `rozkalnsandris/rozkalns_weather@3826175b5bc2c4c7ad1fd5638741258506dd254d`:

- image: `ghcr.io/rozkalnsandris/rozkalns_weather`;
- target alias: `rozkalns-weather-public-rpi5`;
- architecture: `linux/arm64`;
- Compose project/service: `rozkalns-weather-public` / `weather`;
- Compose file: `rozkalns-weather-public.yml`;
- Compose SHA-256: `321fe0aa400d1a01e419f313a6c99ada311058496f36fed032daf1ac036fa16d`;
- operational runtime mode: `private-home`;
- fixed protected runtime config: `/etc/rozkalns-simple-deployer/private/rozkalns-weather-private-home.env` containing only `HOME_LAT` and `HOME_LON`;
- loopback liveness/readiness: `http://127.0.0.1:9180/health` / `http://127.0.0.1:9180/ready`;
- persistent volume: `weather_data`;
- registry profile: `public-anonymous-pull`;
- bounded Compose wait timeout: 180 seconds.

Weather's one-time Phase A/B/C activation is completed historical evidence. Its standing ordinary `AUTO_DEPLOY_SAFE` release path is active for this fixed target only.

### Weather private-home configuration transition (#804)

The target alias/project/service/volume identities remain unchanged. The reviewed Compose now keeps `schema-init` in `public-only`, while `weather`, `public-ingest`, `readiness` and `corpus-check` use static `WEATHER_RUNTIME_MODE=private-home` and the fixed host-owned env file `/etc/rozkalns-simple-deployer/private/rozkalns-weather-private-home.env`.

The protected file is intentionally limited to exactly `HOME_LAT` and `HOME_LON`. It contains no Google/WeatherNext settings and no caller-selected generic environment. Source merge does not create or read this file.

The current private-home candidate is Weather `f658041dfcd6f84994594ddac776b3cf9702e174` at immutable digest `sha256:fc40d6e824be1d0e0783b060f51d9a2a2d1dafdd0b0a3861b39ffdbadcd0dcc6`. The prior read-only live baseline predates this release refresh and is point-in-time evidence only; fresh LIVE preflight must determine whether ordinary SIMPLE-DEPLOY has already reconciled the host before cutover. The one-time source contract `ops/deploy/weather-private-home-cutover-v1.json` therefore requires an explicitly owner-authorized, fixed-service `--force-recreate` transition after atomic private-config/registry/Compose materialization. It preserves the same image digest and persistent `weather_data` volume, performs no schema/data operation, and verifies `/health`, `/ready`, `private-home` mode and coordinate-pair presence without exposing coordinate values.

Any LIVE execution remains separately STRICT-gated; source acceptance does not authorize protected config access, Docker, systemd or runtime mutation.

Private-home activation is split into two owner-gated phases. Phase A (`weather-private-home-cutover-v1.json`) is config/runtime-only: it stops the Weather ingest timer, performs the reviewed private config + registry/Compose + same-digest Weather recreate, verifies `private-home`, restores only the generic SIMPLE-DEPLOY timer, and intentionally leaves `rozkalns-weather-public-ingest.timer` enabled but inactive. Starting that ingest timer during Phase A is forbidden because private-home `ingest-public` is a production SQLite write path.

Phase B (`weather-private-home-data-activation-v1.json`) is separately STRICT-gated for production data. It uses the existing fixed Weather-data helper `--ingest-once`, whose target lock and corpus-integrity guard remain authoritative. After an `INGEST_PASS` receipt, read-only evidence must show at least one home forecast run and value for each exact provider id `icon_d2`, `ecmwf_ifs` and `ecmwf_aifs` without exposing coordinates or forecast values. Only then may the already-enabled recurring ingest timer be started under explicit systemd plus standing recurring-write authority. Because the timer is `Persistent=true`, an immediate catch-up run after start is treated as an authorized recurring production write and must settle successfully before final acceptance.

The #806 hardening adds two mandatory cutover quiesce boundaries:

- `rozkalns-weather-public-ingest.service` must already be `inactive` before the first mutation. The cutover never stops or kills an active ingest run.
- `rozkalns-weather-public-ingest.timer` must be `enabled` + `active` before cutover, is stopped before private config/registry/Compose mutation, and must be observed `inactive` with the ingest service still `inactive` before proceeding.
- the generic `rozkalns-simple-deployer.timer` remains independently quiesced as before.
- only after exact image/source, `/health`, `/ready`, `private-home` mode and home-pair presence all pass may both timers be started in the final fixed re-enable phase.
- any failure or ambiguity after mutation starts remains STOP with no retry, cleanup, rollback or automatic re-quiesce; if failure happens during final timer re-enable, preserve and report the observed timer states instead of claiming they were restored.

The protected parent directory is also deterministic: `/etc/rozkalns-simple-deployer/private` must be a non-symlink directory owned by `root:rozkalns-simple-deployer` with mode `0750`. If absent, it may be created only under the later explicit protected-config mutation authority; if present with different metadata, cutover fails before mutation. Recursive ownership/permission changes are forbidden.

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

## Sanitized Buildx production pointer diagnostics (#926)

The current generic reconciler looks up a reviewed target image via its fixed
`docker buildx imagetools inspect <image>:production` command, with the
existing isolated anonymous Docker profile. A failed pointer command retains
`error_code=POINTER_RESOLUTION_FAILED mutation_started=false`; it now also
emits exactly one `failure_class=<ENUM>` field. The class is advisory
diagnostic evidence, **not** retry, remediation, permission, or release
authorization. The same behavior applies to every reviewed target, including
`rozkalns-cv-rpi5`.

| Public-safe class | Meaning |
| --- | --- |
| `BUILDX_PLUGIN_UNAVAILABLE` | Buildx command or plugin is not recognized |
| `TLS_FAILURE` | Reported TLS or certificate negotiation failure |
| `DNS_FAILURE` | Reported DNS resolution failure |
| `REGISTRY_AUTH_FAILURE` | Reported registry authorization denial |
| `MANIFEST_UNAVAILABLE` | Reported registry manifest/name absence |
| `NETWORK_FAILURE` | Reported connectivity error or network timeout |
| `COMMAND_TIMEOUT` | Bounded subprocess invocation timed out |
| `COMMAND_UNAVAILABLE` | OS could not execute the subprocess |
| `OUTPUT_DECODE_FAILURE` | Subprocess output could not be decoded |
| `UNCLASSIFIED` | Unknown or ambiguous failed command or transport |

Only the predefined enum is printed: no raw stderr, stdout, URLs, tokens,
headers, paths or exception details are surfaced. Matching is conservative,
bounded to the first 8192 characters of failed-command stderr, and has
deterministic specificity ordering. A reported class may be a *symptom*, not
the root cause. If no signal matches, the result must remain `UNCLASSIFIED`.
Malformed success output is still a separate `POINTER_INVALID` contract
failure, and other deploy failure codes are unchanged.

This source change does not execute Docker/Buildx, restart timers, modify
installed runtime code or resolve the CV production pointer failure. Host
installation, execution and any actual deploy require fresh exact-source
evidence and separate owner LIVE authorization.
