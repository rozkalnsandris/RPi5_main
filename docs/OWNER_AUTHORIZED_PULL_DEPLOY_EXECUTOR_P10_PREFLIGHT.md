# Owner-authorized pull deploy executor v1 — P10 Dashboard preflight

Status: SOURCE-ONLY CONTRACT
Roadmap: `RPi5_main#236`
Queue: `ops-workflows#28`
Target: `dashboard-rpi5-production-release`
Exact Dashboard source: `5f7739348f56398d0ba301c9320e1de0062838fc`
Machine contract: `ops/deploy/p10-dashboard-preflight.json`

## Purpose

Freeze the exact read-only preparation and production-PLAN contract for the first P10 Dashboard candidate after the 2026-09-01 trusted-host preflight stopped before `sudo` because the candidate manifest could not find the packaged `node-pty` runtime.

The failure was a preparation-recipe mismatch, not evidence of a Dashboard product/runtime defect. Dashboard exact-source CI builds `node-pty` explicitly from source before staging `apps/terminal-agent/dist/native/node-pty` and generating the production candidate manifest. A generic `npm run check` after ordinary dependency installation is not a sufficient P10 candidate recipe.

This document is source only. It does not authorize host inspection, package installation, `sudo`, production PLAN, `--apply`, deployment, cleanup or retry of any prior preflight.

## Accepted failure evidence

The stopped trusted-host attempt reported:

```text
{"status":"SKIPPED","reason":"native-build-absent","platform":"linux","arch":"arm64"}
{"status":"BLOCKED","error":"ENOENT: no such file or directory, lstat '<candidate>/apps/terminal-agent/dist/native/node-pty'"}
P10_PREFLIGHT=STOP
REASON=candidate_manifest_generation_failed
PLAN_VALIDATED=NO
PRODUCTION_MUTATION_STARTED=NO
P10_APPLY_EXECUTED=NO
RETRY_ALLOWED=NO
```

The failed authorization is not reusable. No privileged PLAN was entered and no production mutation occurred.

## CI-parity candidate preparation

Before any future privileged PLAN, prepare one fresh unprivileged workspace at exact Dashboard SHA `5f7739348f56398d0ba301c9320e1de0062838fc` with Node major 24.

Existing host prerequisites are checked only for presence. The P10 preflight may not install or upgrade packages. Required tools are Node 24, npm, git, make, Python 3 and an available C++ compiler (`c++` or `g++`). A missing prerequisite is a STOP and requires a separate owner decision if host/package mutation is needed.

The preparation order is normative:

```text
npm ci --ignore-scripts
npm audit --audit-level=high
npm_config_build_from_source=true npm rebuild node-pty --dangerously-allow-all-scripts --foreground-scripts
npm run typecheck
npm run lint
npm run test
npm run build
node tools/package-terminal-native-runtime.mjs --root .
node tools/production-candidate-manifest.mjs --root . --sha 5f7739348f56398d0ba301c9320e1de0062838fc > <fresh-candidate-manifest-path>
node tools/production-candidate-manifest.mjs --root . --sha 5f7739348f56398d0ba301c9320e1de0062838fc --verify <fresh-candidate-manifest-path>
node tools/production-runtime-smoke.mjs --root . --manifest <fresh-candidate-manifest-path> --sha 5f7739348f56398d0ba301c9320e1de0062838fc
```

The explicit `node-pty` rebuild must happen before typecheck/test/build/staging. Manifest generation requires the staged native runtime. `native-build-absent`, missing staged runtime, manifest verification failure or runtime-smoke failure is a STOP before privileged execution.

No candidate-preparation command uses `sudo`, `apt`, `apt-get`, `--apply` or an acknowledgement flag.

## Installed controller identity selection

The privileged executable remains only the canonical installed controller:

```text
/opt/dashboard_RPi5/current/tools/production-release-controller.mjs
```

Never execute privileged JavaScript from the operator-writable candidate workspace and never replace/patch the installed controller merely to make preflight proceed.

Before `sudo`, classify the bytes reached through the canonical path using the Git blob algorithm, not plain-file SHA-1:

```text
git hash-object --no-filters /opt/dashboard_RPi5/current/tools/production-release-controller.mjs
```

Exactly two reviewed identities are accepted:

- `c0566adb76e044632a4556dbefeb0f46839b4996` — current symlink-safe controller; use ordinary `/usr/bin/node`;
- `7fcc58cbea2f1247d6e4d93bc3805923697fbfab` — reviewed legacy controller; use `/usr/bin/node --preserve-symlinks-main`.

Any other, unreadable or ambiguous identity is a STOP before privileged invocation.

This is a preselected compatibility branch, not a retry/fallback mechanism. Identity selection occurs before `sudo`, and a future authorization permits at most one privileged PLAN attempt.

## PLAN-only contract

A future fresh explicit STRICT P10 PREFLIGHT authorization may permit exactly one PLAN-only call through the canonical controller selected above, with:

- exact candidate root;
- exact fresh manifest path;
- exact source SHA `5f7739348f56398d0ba301c9320e1de0062838fc`;
- no `--apply`;
- no acknowledgement;
- no controller-path switching after invocation.

Exit code zero alone is not success. The stdout must parse as the reviewed PLAN JSON contract and bind:

- `status=PLAN`;
- `sourceSha=5f7739348f56398d0ba301c9320e1de0062838fc`;
- exact `candidateSha256` matching the verified manifest;
- `observedCurrent` as a 40-character SHA or `none`;
- reviewed `targetRelease` state;
- reviewed planned `operations`.

The fixed production apply-lock may be observed only under the separately authorized read-only envelope. It may not be cleared, repaired or otherwise mutated.

## Failure semantics

Any error or ambiguity during the future preflight means public-safe evidence + STOP. Specifically:

- no second privileged PLAN attempt;
- no alternate controller path;
- no retry under the consumed authorization;
- no package installation;
- no controller replacement;
- no apply-lock cleanup;
- no candidate-checkout privileged execution;
- no `--apply`;
- no production deployment or other runtime mutation.

## Queue transition

`ops-workflows#28` remains `WAITING_STRICT_READ_ONLY_PRODUCTION_PLAN_BASELINE` until all of the following are true:

1. this source repair is explicitly merged and resulting exact `RPi5_main/main` CI is green;
2. Dashboard remains exact `5f7739348f56398d0ba301c9320e1de0062838fc` with exact-source CI green;
3. a new separately authorized P10 preflight completes the CI-parity candidate preparation;
4. installed controller identity is bound to exactly one reviewed blob;
5. exactly one PLAN returns valid reviewed JSON;
6. public-safe apply-lock evidence is bound;
7. GitHub source/queue/CI are freshly revalidated after PLAN.

Only then may #28 be reconciled from WAITING to READY. READY remains eligibility only. P10 production APPLY requires a later separate exact LIVE authorization bound to the successful PLAN values.

## Regression boundary

`tests/test-deploy-executor-p10-preflight-recipe.py` locks the machine contract into `make validate`. It specifically protects:

- exact Dashboard SHA and queue identity;
- Node 24 and non-mutating prerequisite policy;
- `npm ci --ignore-scripts` before the explicit source rebuild;
- exact `npm_config_build_from_source=true npm rebuild node-pty ...` step;
- explicit native runtime staging before manifest generation;
- manifest generation + verification + runtime smoke;
- Git-blob controller identity rather than `sha1sum`;
- the two reviewed controller identities and legacy-only `--preserve-symlinks-main` branch;
- one PLAN attempt, parsed PLAN receipt requirement and fail-closed no-retry/no-apply semantics.
