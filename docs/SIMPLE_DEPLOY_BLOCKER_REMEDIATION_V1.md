# SIMPLE-DEPLOY target-blocker remediation design (#60)

Status: **SOURCE-ONLY / BLOCKED_NO_TIMER_START**. This is an additive design and deterministic regression contract, not an installed runtime guard, materializer, cutover executor or permission to run diagnostics with Docker.

Machine contract: `ops/contracts/simple-deploy-blocker-remediation-v1.json`.
Parent gate: `ops/contracts/simple-deploy-timer-restoration-v1.json`. Preserve its nine mandatory all-five-target safety gates and the disabled/inactive SIMPLE-DEPLOY timer. Enabling a timer with elapsed `OnBootSec=2min` can trigger an immediate `--all` reconciliation, not a two-minute safe window.

## Evidence boundary: 2026-10-10, not continuous production truth

Source baseline `5850fd707464a9f2c9dfcd472903d867276d4f86`. Separately authorized, sanitized, read-only metadata established that the executor upgrade was installed, the timer was disabled/inactive, both Hermes Compose files were absent and both Hermes targets had no successful SIMPLE-DEPLOY receipt. Weather, CV and Coloring Pages retained receipts. Current anonymous GHCR `production` pointers were readable through pull-scoped in-memory Bearer authentication. The Weather and Coloring Pages pointers matched their last success receipts; the CV pointer was **DIFF**. This does not prove the actual running Docker image, current publisher quiescence or future state.

The historical initial GHCR HTTP 401 is a normal Registry v2 Bearer-challenge step, **not** evidence of an absent image. Never capture the challenge, raw server reply, authorization header or ephemeral token in a public artifact.

## Hermes Deals: private-parent conflict must be fixed at source

The **observed existing shared** `/etc/rozkalns-simple-deployer/private` is a real directory, `root:rozkalns-simple-deployer`, mode `0750`, as the Weather private-home contract requires. Historical Hermes v2 materialization inherited by v3 expects `root:root` with mode `0700` for that parent. Those expectations conflict: **do not chown, chmod, recreate, replace or weaken the shared parent to make Hermes pass**. Doing so can break Weather and alter another app's protected configuration boundary.

A subsequent separately reviewed Hermes materializer source revision must explicitly recognize **the exact existing Weather-compatible parent** and fail closed on any other identity/mode; it must preserve root-owned protected child content and check that the exact intended execution principal can safely consume the child without broadening access. This design does not assert that child readability is already solved. The source revision must preserve the former v1/v2/v3 contracts as historical evidence, root-safe Git verification, the failed trusted checkout and no-retry/no-cleanup semantics.

The Hermes Deals fixed state/config/data and private env destinations were observed **ABSENT**; an absent destination is not an approved materialization. The runtime state parent was separately observed correctly runtime-principal-owned with `0700`. Future privileged **metadata-only** classification must distinguish `ABSENT`, `EXACT_READY`, `PARTIAL_CONFLICT` and `PRIVILEGED_METADATA_REQUIRED`. Only after a source solution, tests and separate owner LIVE authority may prerequisite materialization and then first SIMPLE-DEPLOY adoption be considered. No database, credential, broad permissions or service mutation is implicitly included.

## Hermes Tech: distinguish legacy health from the new cutover

The legacy `hermes-tech-web.service` and `hermes-tech-pull-deploy.timer` were active. Fixed `/health` and `/ready` probes on the legacy loopback origin returned HTTP **404**, while the **post-cutover** SIMPLE-DEPLOY registry and `ops/deploy/hermes-tech-simple-deploy-cutover-v1.json` require **200** for both. A legacy HTTP 404 is not proof that the existing site is down, and it must never be treated as proof that the new Compose service passed health.

Preserve the existing health paths and required 200 statuses; do **not** change the new target registry to 404/optional, stop the legacy web service, retire the legacy timer or claim port ownership has changed under this design. Any future exact owner LIVE cutover must separately verify legacy ownership, quiesce the legacy timer/service in the reviewed order, prove no parallel loopback port ownership, materialize the exact Compose adapter, reconcile the immutable image digest, then prove both HTTP 200 and a new success receipt. Unknown or failed postconditions mean STOP without automatic retry, rollback or cleanup.

## CV: classify pointer failure without Docker mutation

The current source executor uses `docker buildx imagetools inspect` for the `production` pointer. Earlier CV status recorded `PRE_MUTATION_FAILURE / POINTER_RESOLUTION_FAILED` with `mutation_started=false`, but did **not** persist a sanitized `failure_class`. The host's `docker-buildx-plugin` package and a system CLI plugin executable are present, which **does not establish** CLI execution or registry behavior under the deployer's context.

An independently scoped anonymous OCI pull-only HEAD successfully resolved a CV `production` digest **different** from the historical last-success receipt. That supports **pointer/receipt drift**, not a determination that Buildx caused the historical failure, that the new digest is running, or that a new deploy is allowed. No Docker, Buildx, Compose or reconciling `--all` command is part of this design.

A future separate source revision may preserve only one allowlisted `failure_class` value from the existing fail-closed `_classify_pointer_stderr` path in the status receipt, with synthetic adversarial regression tests proving no raw stderr, registry challenge, token, credentials or path leaks. Treat old missing subtype as **UNKNOWN**, not a retroactively inferred cause. Any future live command or single-target release reconciliation requires a separate owner scope, exact immutable digest, no in-flight mutation and current health acceptance. Do not use image-pointer mismatch as deployment authorization.

## Global acceptance and later owner gates

Timer remains **BLOCKED_NO_TIMER_START**. The five-source-target set is never reduced by a runtime registry override and the scheduler is never enabled until every target is installed, health-checked, digest/receipt-current and independently adopted. Source design completion cannot close #60 Phase 8 operational gate or claim a production rollout.

Next independently reviewable source outcomes: (1) compatible Hermes materializer with synthetic tests, (2) Hermes Tech immutable-digest cutover validation, (3) CV sanitized failure-class persistence if justified. Their real filesystem, service, Docker, protected-data or Cloudflare effects are separate STRICT LIVE decisions. No automatic retry, rollback, cleanup, historical checkout repair or permission adjustment is allowed here.

Official documentation:
- [systemd.timer OnBootSec expiry](https://man7.org/linux/man-pages/man5/systemd.timer.5.html)
- [Docker Buildx imagetools inspect](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/)
- [Distribution v2 Bearer token flow](https://github.com/distribution/distribution/blob/main/docs/content/spec/auth/token.md)

Production deploy/change REQUIRED: NO for this source-only design. No MERGE, LIVE, Docker, systemd, Cloudflare, configuration, credential or permissions mutation is included.
