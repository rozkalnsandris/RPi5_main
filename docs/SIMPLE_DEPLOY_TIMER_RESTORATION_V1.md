# SIMPLE-DEPLOY five-target timer restoration design (#60)

Status: SOURCE-ONLY. No standing LIVE authority or installed runtime guard.
Machine contract: ops/contracts/simple-deploy-timer-restoration-v1.json.
This design does not install a script, change the timer, edit the registry, execute Docker or authorize deployment.

## Why restoration remains BLOCKED

On the 2026-10-10 source baseline c6f1b747f371aa83dbd5c557a499b01f3161a748, the reviewed registry is execution_enabled=true with five targets. The existing systemd service executes the reconciler with --all. The timer has OnBootSec=2min, OnUnitInactiveSec=2min and Persistent=true. If OnBootSec has already elapsed when activated, systemd may start the service immediately: there is no guaranteed two-minute safe window.

The separately authorized, sanitized 2026-10-10 status triage was:

| Reviewed target | Last result | Last success receipt | Outstanding problem |
| --- | --- | --- | --- |
| rozkalns-weather-public-rpi5 | SUCCESS | Present | Current production pointer and health not reconfirmed |
| hermes-deals | PRE_MUTATION_FAILURE / COMPOSE_CONTRACT_INVALID | Absent | Installed Compose and initial authorized cutover missing |
| hermes-tech-public-rpi5 | PRE_MUTATION_FAILURE / COMPOSE_CONTRACT_INVALID | Absent | Installed Compose and initial authorized cutover missing |
| rozkalns-cv-rpi5 | PRE_MUTATION_FAILURE / POINTER_RESOLUTION_FAILED | Present | Pointer failure root cause unresolved |
| coloring-pages-public-rpi5 | SUCCESS | Present | Current production pointer and health not reconfirmed |

All five last-status blocked values were false. That does NOT establish activation readiness. SUCCESS with historical mutation_started=true describes a completed prior operation, not a current in-flight write. Missing installed Hermes Compose files are independent of source registry entries.

Direct anonymous GHCR manifest HEAD returned HTTP 401 for Weather, CV and Coloring Pages. Registry V2 normally responds with a Bearer challenge before an anonymous pull-scoped token can be used. Initial HTTP 401 is neither an image-absence verdict nor a digest comparison. The token, challenge, and raw server responses must not be published. Any future credential-free, pull-scoped, in-memory challenge flow is separately scoped read-only work; this design does not execute it.

## Mandatory default-deny gates

1. EXACT_SOURCE_AND_HOST_PROVENANCE: Freshly bind the exact current RPi5_main HEAD, reviewed registry, installed executor SHA, systemd unit identity and provenance. Source readiness is not production state.
2. ELAPSED_ONBOOT_MAY_TRIGGER_IMMEDIATELY: Model timer enable/start as potentially causing an immediate --all run. No inspection may be deferred until after timer start.
3. ALL_INSTALLED_TARGETS_REVIEWED_AND_ADOPTED: All five registry targets need installed, hash-verified, root-owned Compose and separate approved first target adoption. Do not silently omit missing Hermes targets. Any proposed smaller schedule requires a separate reviewed source and later explicit LIVE installation; never edit live registry or inject a timer override as a shortcut.
4. ALL_CURRENT_STATUSES_RECEIPTS_AND_HEALTH_VALID: Require valid sanitized status and receipt identities, latest SUCCESS or NO_OP_CURRENT, blocked=false, absence of STOP_ERROR and unresolved PRE_MUTATION_FAILURE, current app health/readiness evidence and last successful immutable digest. A receipt file alone is insufficient.
5. OCI_POINTER_VERIFIED_AFTER_ANONYMOUS_CHALLENGE: Resolve all production pointers with an approved, bounded, anonymous read-only OCI protocol where possible. HTTP 401 at initial HEAD remains indeterminate; no token or raw challenge disclosure; no Docker, Buildx, Compose or mutating reconciler used as a diagnostic shortcut.
6. NO_PENDING_MUTATION_AT_HANDOFF: Every current production digest must equal its last accepted receipt digest at the time of handoff, and current release publishing must be quiescent. A mutable tag can race with a timer firing. Any intentional standing automatic-release exposure requires a fresh owner risk decision naming affected targets; it is never implied by this restoration.
7. QUIESCENT_TIMER_SERVICE_AND_NO_JOBS: Prove timer disabled/inactive/dead, service inactive/dead, no pending job or daemon reload, and no other target deployment in progress. Revalidate protected state using separately authorized sanitized read-only evidence.
8. EXACT_SEPARATE_OWNER_LIVE_AUTHORIZATION: Only after all gates pass may the owner separately authorize a bounded RPi5 timer enable/start and associated potential reconciliation effects with exact source, target scope, baseline, fail-closed recovery and post-verification. No merge automatically grants this.
9. POST_ACTIVATION_SANITIZED_ACCEPTANCE: Under separate authority prove the timer active/waiting, expected oneshot service lifecycle, absence of unapproved Docker changes, and per-target sanitized states and health after any immediate firing. Unexpected results mean STOP; no implicit retry, disable, rollback, cleanup or broad repair.

Any unknown, stale, absent or contradictory gate is BLOCKED_NO_START. There is no runtime implementation of these gates in this PR. This is a safety decision model, not evidence that any blocker has already cleared.

## Remediation order (not executed)

- Install and adopt Hermes Deals and Hermes Tech under their own exact scope and LIVE permissions, including verified first-deployment receipts.
- Investigate the CV pointer failure with the already upgraded executor's sanitized failure classifier; never rerun the mutating --all service merely to diagnose Buildx.
- Obtain allowed, sanitized anonymous OCI digest comparison for Weather, CV and Coloring Pages and prove current health. Do not infer package visibility from initial HTTP 401.
- Complete all nine gates from a fresh point-in-time snapshot, then consider separately authorized timer lifecycle and side-effect acceptance.

Public source references: docs/SIMPLE_DEPLOY_HOST_V1.md, docs/INGRESS_PHASE8_OPERATIONS_V1.md, ops/contracts/simple-deploy-host-v1.json, ops/deploy/simple-deploy-targets-v1.json.

Official references:
- https://man7.org/linux/man-pages/man5/systemd.timer.5.html
- https://man7.org/linux/man-pages/man1/systemctl.1.html
- https://github.com/distribution/distribution/blob/main/docs/content/spec/auth/token.md

Production deploy/change REQUIRED: NO for this source-only design. No LIVE mutation, Docker execution, timer lifecycle, credentials, raw logs or private configuration is authorized.
