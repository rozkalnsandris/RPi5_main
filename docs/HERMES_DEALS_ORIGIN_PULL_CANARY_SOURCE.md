# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE-REGISTERED / #366 MERGED / CANONICAL SOURCE-INTEGRATION DRAFT / GLOBALLY EXECUTION-DISABLED / NOT HOST-EXECUTABLE**

Tracking:

- completed source prerequisite: `RPi5_main#365` / merged PR #366 at `13c0c46e9966b0682b53553a92bed510cf491c86`
- current work item: unmerged Hermes canonical source-integration draft
- completed broker installation/wiring gate: `RPi5_main#363` / PR #364
- completed dispatcher gate: `RPi5_main#361` / PR #362
- completed helper binding: `RPi5_main#359` / PR #360
- completed privileged consumer: `RPi5_main#356` / PR #357
- completed identity-only request: `RPi5_main#354` / PR #355
- completed registry reconciliation: `RPi5_main#352` / PR #353
- runner-independent helper: `hermes-deals#834` / PR #840
- residual Hermes runner migration: `hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Current routing

Phase 4 remains the residual Hermes Deals origin-audit migration. The production registry contains `hermes-deals.origin-path-audit.v1` but remains globally `execution_enabled=false`. The operation remains STRICT, ordinary LIVE-ALL eligibility is false, rollback policy is `NONE`, invocation budget is one future read-only audit, and adapter `apply()` remains fail-closed.

No source merge in this lane authorizes host installation, helper execution, canary execution or runner retirement.

## Current cross-repository anchors

At #365 creation:

- `RPi5_main/main = 9c60248547043ee5ae7b1d0e2897fd9b8aac381a`;
- exact-main Validate #820, FAST-LANE #276 and GITHUB-ONLY #264 are SUCCESS;
- current `hermes-deals/main = 511c1566111983f809bc958bc4b68510771d3efb`;
- that Hermes head is a verified docs-only bot commit with parent `2f47f64ab15e767f4e53ad182326e64e313d5094`;
- runner-independent helper blob remains exact `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673` on current Hermes main;
- Hermes repository ID is `1317143994`.

No commit-associated workflow runs were returned for the current Hermes docs-only head, so historical CI is not promoted to current-head evidence. The unchanged helper blob is the reviewed helper provenance anchor for #365.

These values prove source identity only, never actual host/runtime state.

## Identity-only request and canonical derivation

The broker request remains exactly:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

Caller-supplied source SHA, `as_of`, command, shell, capability, executable/path, argv, environment, UID/GID, systemd unit, URL, output/evidence path or prebuilt dispatch plan is forbidden.

The existing consumer contract revalidates complete canonical evidence twice with sanitized host evidence between the reads. `registered_source_sha` comes only from the revalidated source evidence; `as_of` is the UTC date of the validated owner authorization server-side `created_at`.

## Completed broker boundary

#363/#364 source-binds the dedicated UNIX socket and root service while preserving the unprivileged poller boundary:

- `/run/rozkalns-hermes-deals-origin-broker/request.sock`;
- root owner, `rozkalns-deploy-executor` group, mode `0660`;
- `Accept=yes`, `MaxConnections=1`;
- fixed root service `rozkalns-hermes-deals-origin-broker@.service`;
- fixed broker entrypoint `/usr/local/libexec/rozkalns-hermes-deals-origin-broker`;
- poller `NoNewPrivileges=true` unchanged;
- generic `rozkalns-deploy-dispatch` still disabled.

The broker entrypoint remains inert in #365. It is not wired to a real helper launch.

## #365 read-only GitHub source composition

The existing Source App provider model is reused rather than duplicated. #365 source-binds:

- App ID `4537106`;
- installation ID `152422751`;
- owner `rozkalnsandris` / owner ID `277435981` / type `User`;
- selected-repository installation posture;
- repository `rozkalnsandris/hermes-deals` / ID `1317143994`;
- token scope exactly one repository;
- requested permissions exactly `Actions:read + Contents:read`;
- no write permission accepted;
- expected short installation-token lifetime.

`hermes_deals_origin_source_auth.py` fixes the repository in source so no runtime caller can select a repository or permission set.

This is source composition only. It does not prove or mutate the actual App installation, selected repository set, private key, credential path or runtime token behavior on RPi5.

## #365 fixed helper launch contract

`hermes_deals_origin_helper_launch.py` adds a one-shot launch abstraction that first calls the reviewed `prepare_hermes_deals_origin_privileged_dispatch()` path. A socket caller cannot pass a prebuilt plan or override executable/argv/environment.

The launch source fixes:

- helper `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- helper blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- exactly two canonical arguments: `registered_source_sha`, `as_of`;
- `shell=False`;
- source-fixed minimal environment;
- timeout 50 seconds;
- stdout/stderr limits 4096 bytes each;
- one invocation budget;
- accepted helper exit codes only 0/1/2;
- exact helper stdout identity and explicit false production DB/deploy/restart flags.

CI injects a fake runner. The real helper/audit is never executed in source tests.

`HELPER_PROCESS_LAUNCH_IMPLEMENTED=true` means the fixed source primitive exists; `HELPER_PROCESS_LAUNCH_WIRED=false` means no production broker path can invoke it yet.

## Concrete canonical revalidator is still missing

Demand-driven #365 inspection proved `CanonicalHermesOriginRevalidator` and `SanitizedHermesOriginHostEvidenceResolver` are currently Protocol/test seams, not production compositions.

This is now the blocking source prerequisite after #365. The next source integration gate must implement/review those concrete components from the existing isolated LIVE-AUTH, READY queue, registry, source/CI and sanitized host-evidence contracts, then bind them to the broker entrypoint without expanding caller authority.

Therefore **LIVE is not the next gate after #365 merge**. A separate integration source merge and fresh exact-main/cross-repository evidence must come first.

## Installation manifest

`ops/deploy/hermes-deals-origin-broker-installation.json` is source evidence only. During #365 it records:

- `issue=365`;
- `source_baseline=9c60248547043ee5ae7b1d0e2897fd9b8aac381a`;
- `eligible_source_sha=null`;
- `live_install_eligible=false`;
- source-auth composition implemented but runtime credential/install proof false;
- helper process launch implemented but not wired;
- concrete canonical revalidator implemented false.

No host file is created or changed by this PR.

## Static selector and legacy runner remain unchanged

The production registry remains globally disabled and its existing operation registration/legacy path is not switched by #365. The existing origin-audit workflow/self-hosted runner remains the residual path until a replacement is separately source-complete, installed, activated and proven. The separate `hermes-deals-release` runner remains out of this origin-audit lane.

## Required regression contract

Focused tests must prove:

1. Hermes source provider uses only repo ID `1317143994` with `Actions:read + Contents:read` and one-repository token scope;
2. unexpected permissions, write permissions, wrong App/install/owner/repository/token scope fail closed;
3. caller authority remains only `authorization_issue_number`;
4. helper launch reuses the canonical dispatcher preparation path and therefore the double revalidation contract;
5. executable, two arguments, environment, timeout and output limits are source-fixed;
6. arbitrary path/argv/env/command/capability injection is impossible through the request;
7. at most one helper invocation occurs;
8. timeout, runner failure, non-0/1/2 exit, stderr, oversized or identity-drifted stdout fail closed;
9. real helper/audit execution never occurs in CI;
10. broker entrypoint remains unwired and host/LIVE flags remain false;
11. existing poller and generic dispatcher safety posture is unchanged.

## Next gates

1. Finish #365 / PR #366 through exact-head CI/review and Ready; STOP for separate `MERGE RPi5_main #366`.
2. After any separately authorized merge, refresh exact-main CI and cross-repository helper provenance.
3. Open a **separate source integration gate** for concrete canonical Hermes revalidator + sanitized host-evidence resolver + broker-entrypoint composition.
4. Merge that gate separately and require fresh exact-main/cross-repository evidence.
5. Perform read-only runtime preflight for App installation/credential/helper/unit identities.
6. Only then may a separate explicit LIVE authorization install/activate reviewed host components.
7. A separate STRICT authorization is required for exactly one genuine read-only origin audit canary.
8. Runner retirement remains later and separately LIVE-authorized.

## Required false state during #365

`GLOBAL_EXECUTION_ENABLED=false`

`SOURCE_READ_AUTHORITY_PROVEN=false`

`CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=false`

`HELPER_PROCESS_LAUNCH_WIRED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`LIVE_INSTALL_ELIGIBLE=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`RUNNER_RETIREMENT_ELIGIBLE=false`

`PRODUCTION_MUTATION_STARTED=false`

## Source-integration supersession after merged #365/#366 (2026-09-04)

This section supersedes the earlier current/next-gate wording while retaining it as historical evidence. GitHub freshly reports PR #366 merged as `13c0c46e9966b0682b53553a92bed510cf491c86`; refreshed local `main` matches. Hermes `main` remains `511c1566111983f809bc958bc4b68510771d3efb`, and the reviewed helper blob remains `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

The current unmerged source patch implements the concrete canonical revalidator, strict sanitized host-evidence resolver and inert broker composition. It preserves the identity-only request, mandatory double canonical revalidation, fixed Hermes repository, exact Source App scope, fixed helper path/two-argument interface, fake-runner-only CI seam and all bounded launcher limits.

Host observation fields are limited to: version/correlation/freshness; canonical operation and source SHA; fixed registration identity; fixed broker/socket/service identities; public credential location metadata; fixed pull-helper identity/interface; fixed probe/dispatcher/workflow source identities; and explicit negative secret/mutation/authority flags. The resolver emits none of the paths, unit names or credential metadata to the caller-facing result.

Repository source does not prove actual runtime state. The entrypoint remains inert, no helper/audit can execute from it, and no credential/App permission, file, service, runner, database or application state is inspected or changed.

`CURRENT_WORK_ITEM=HERMES_CANONICAL_SOURCE_INTEGRATION_DRAFT`

`CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=true`

`SANITIZED_HOST_EVIDENCE_RESOLVER_IMPLEMENTED=true`

`BROKER_COMPOSITION_IMPLEMENTED=true`

`BROKER_ENTRYPOINT_WIRED=false`

`SOURCE_READ_AUTHORITY_PROVEN=false`

`HELPER_PROCESS_LAUNCH_IMPLEMENTED=true`

`HELPER_PROCESS_LAUNCH_WIRED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`LIVE_INSTALL_ELIGIBLE=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`RUNNER_RETIREMENT_ELIGIBLE=false`

`PRODUCTION_MUTATION_STARTED=false`

Next sequence: finish this source integration and Draft PR → separate MERGE → fresh exact merged-source/CI/helper validation → read-only runtime preflight → separate LIVE installation authorization → later separate STRICT one-canary authorization → later separate runner-retirement authorization.

## Post-#368 merged-source supersession (2026-09-04)

PR #368 is merged at exact `RPi5_main/main = 2550e77f6cb811ca6f10b49ef0b2fef554d64869` with exact-main Validate #833, FAST-LANE #289 and GITHUB-ONLY #277 successful. Hermes remains `511c1566111983f809bc958bc4b68510771d3efb` and the reviewed helper blob remains `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

`CURRENT_WORK_ITEM=HERMES_RUNTIME_PREFLIGHT_PREPARATION`
`ELIGIBLE_SOURCE_SHA=2550e77f6cb811ca6f10b49ef0b2fef554d64869`
`SOURCE_INTEGRATION_MERGED=true`
`SOURCE_READ_AUTHORITY_PROVEN=false`
`BROKER_ENTRYPOINT_WIRED=false`
`HELPER_PROCESS_LAUNCH_WIRED=false`
`LIVE_INSTALL_ELIGIBLE=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

The one-canary gate is still not authorized. Before any LIVE installation or genuine audit execution, the next separate step is a bounded read-only runtime preflight proving the expected adapters and public-safe identity/metadata contract without reading credential contents.

## Current supersession — Hermes broker-entrypoint wiring source gate (2026-09-06)

This section supersedes earlier broker-entrypoint next-action wording. Accepted #191 evidence records both prerequisite runtime proofs on exact reviewed source: the root read-only runtime-adapter preflight returned `HERMES_ORIGIN_RUNTIME_ADAPTERS_READY`, and the separately owner-authorized protected Source App proof returned `HERMES_SOURCE_APP_SCOPE_PROVEN` for exactly `rozkalnsandris/hermes-deals`, one selected repository, and only `actions:read` + `contents:read`. Those are runtime evidence records; repository source does not recreate or broaden either authorization.

This source gate wires the broker entrypoint to a zero-argument fixed runtime factory. The socket caller still controls only `authorization_issue_number`. The factory fixes the isolated authorization surface, execution-disabled operation registry, executor read-client credential, Hermes source credential, source repository, replay store, sanitized host-observation provider and capability-specific helper runner. No repository, SHA, path, command, argv, environment, unit, UID/GID, App, installation or permission selector is accepted from the caller.

The replay boundary is now explicit: the same `ConcreteDurableHermesOriginReplayAuthority` instance is shared with the canonical revalidator; exactly two successful canonical availability checks must precede one durable `consume()`; the consume attempt occurs before helper launch; and once the consume boundary is entered the authorization is non-reusable even if helper execution later fails. Only after a valid `CONSUMED` receipt may the fixed one-shot helper runner start. Public broker receipts expose only allowlisted failure stages and bounded identity/result fields, never token or private-key content.

This is still source readiness, not live activation. The currently installed broker entrypoint is expected to remain the older inert blob until a later separately reviewed upgrade. The current service sandbox uses `ProtectSystem=strict` with no replay-store writable path, while durable consume requires a write to `/var/lib/rozkalns-deploy-executor-p9`. Therefore this source gate deliberately keeps `LIVE_INSTALL_ELIGIBLE=false`; it does not alter the service unit, installed files, socket state, credentials or runtime permissions.

`PHASE4_CURRENT_WORK_ITEM=HERMES_ORIGIN_BROKER_ENTRYPOINT_WIRING_SOURCE`
`BROKER_ENTRYPOINT_WIRED=true`
`HELPER_PROCESS_LAUNCH_WIRED=true`
`DURABLE_REPLAY_CONSUME_BEFORE_HELPER=true`
`CALLER_AUTHORITY=authorization_issue_number`
`CURRENT_INSTALLED_ENTRYPOINT_UPGRADED=false`
`CURRENT_SERVICE_REPLAY_WRITE_AUTHORITY_PROVEN=false`
`LIVE_INSTALL_ELIGIBLE=false`
`PRIVILEGED_DISPATCH_ENABLED=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

Current sequence: source review/Draft PR/CI/Ready → explicit MERGE → fresh exact merged-source validation → a separate source gate for exact broker/runtime upgrade provenance plus the minimum replay-store write permission required by durable consume → separate MERGE → trusted-checkout convergence and root read-only upgrade preflight → separate explicit LIVE runtime upgrade → read-only post-upgrade verification → only then a separate STRICT authorization for one genuine read-only audit canary. Runner retirement remains a later independent LIVE gate.

## Current supersession — Hermes broker runtime upgrade/provenance source gate (2026-09-06)

- `PHASE4_CURRENT_WORK_ITEM=EXACT_BROKER_RUNTIME_UPGRADE_PROVENANCE_AND_MINIMAL_REPLAY_WRITE_PERMISSION`.
- Source runtime uses a fixed one-operation Hermes registry; the global P9 operation registry is neither read nor mutated by the broker runtime.
- The broker service grants only `ReadWritePaths=/var/lib/rozkalns-deploy-executor-p9`, required for durable replay SQLite/WAL consume.
- The reviewed upgrade operator is `scripts/install-hermes-deals-origin-broker-runtime-upgrade.py`; default mode is root read-only preflight and `--apply` requires a separate exact owner LIVE authorization.
- Exact upgrade surface: 5 reviewed old-blob replacements + 6 absent-only Hermes runtime creates; 16 shared executor files are read-only exact-blob prerequisites.
- Apply ordering is fixed: repeat preflight → stop broker socket → verify exact inactive/no active instance → file upgrade → revalidate prerequisites → daemon-reload → start socket → verify active/enabled.
- No automatic retry, rollback, cleanup, global registry mutation, credential mutation, replay consume, helper execution, genuine audit, runner retirement, deploy, or production-data mutation is authorized by this source gate.
- `BROKER_ENTRYPOINT_WIRED=true`.
- `CURRENT_SERVICE_REPLAY_WRITE_AUTHORITY_PROVEN=false`.
- `RUNTIME_UPGRADE_PREFLIGHT_PROVEN=false`.
- `RUNTIME_UPGRADE_APPLIED=false`.
- `LIVE_INSTALL_ELIGIBLE=false`.
- `PRODUCTION_MUTATION_STARTED=false`.
- After merge: converge the trusted checkout, run the root read-only upgrade preflight, then STOP for a separate exact LIVE runtime-upgrade authorization.

## Current supersession — failed Hermes one-canary evidence-write recovery source gate (2026-09-06)

The first genuine broker canary used READY queue `ops-workflows#30` and owner-authored `deploy-authorizations#9` for reviewed Hermes source `2f47f64ab15e767f4e53ad182326e64e313d5094`. The broker completed canonical preparation and durable replay consume, then returned sanitized `FAIL_CLOSED` at `safe_stage=helper_launch` with `authorization_reuse_forbidden=true`. That queue/authorization pair is permanently non-reusable; this source gate authorizes no retry, replay reset, cleanup or second canary.

Source review plus the documented systemd sandbox semantics identify the missing capability: the broker service preserves `ProtectSystem=strict`, but the applied runtime unit allowlists only `/var/lib/rozkalns-deploy-executor-p9` while the reviewed helper persists sanitized audit evidence below the fixed machine root `/var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5`. The fix keeps the filesystem read-only by default and adds only that machine-specific evidence root to `ReadWritePaths=`. No broader `/var/lib`, `/var/lib/hermes-deals-audits`, home, credential or arbitrary path write authority is added.

The service-unit Git blob change must be paired with `hermes_deals_origin_runtime_adapters.py`, because the host-observation adapter validates the installed service unit by exact reviewed blob. The recovery mutation surface is therefore exactly two replacements: current runtime adapter `456fea3d6969975d0fd432d20089772f28b63ec7` → `21918e96495592b6a3478e8e74ae06fdf640121d`, and current service unit `21319746d1e32f2b67f701f0a22174bfb0542987` → `2f4874323a92610d4d91df719a97688bc880fc48`. Twenty-five other installed broker/executor files are immutable exact-blob prerequisites.

The reviewed recovery operator is `scripts/install-hermes-deals-origin-broker-evidence-write-recovery.py`. Default mode is root read-only preflight; it additionally requires the fixed evidence parent and `rpi5` directory to be real `root:root 0700` directories before any future write permission upgrade. `--apply` remains a separate explicit LIVE gate. Apply ordering is double preflight → stop socket → replace exactly two files → revalidate prerequisites → daemon-reload → start socket → verify active/enabled. There is no automatic retry, rollback or cleanup.

`PHASE4_CURRENT_WORK_ITEM=HERMES_ORIGIN_BROKER_EVIDENCE_WRITE_PATH_RECOVERY`
`FAILED_CANARY_QUEUE=30`
`FAILED_CANARY_LIVE_AUTH=9`
`FAILED_CANARY_DURABLE_REPLAY_CONSUMED=true`
`FAILED_CANARY_AUTHORIZATION_REUSE_FORBIDDEN=true`
`FAILED_CANARY_RETRY_AUTHORIZED=false`
`PROTECT_SYSTEM_STRICT_PRESERVED=true`
`SOURCE_SERVICE_WRITE_PATHS=REPLAY_STATE_PLUS_FIXED_RPI5_EVIDENCE_ROOT`
`RECOVERY_PREFLIGHT_PROVEN=false`
`RECOVERY_APPLIED=false`
`LIVE_RECOVERY_ELIGIBLE=false`
`GENUINE_HERMES_AUDIT_ACCEPTED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

After this source gate: review/Draft PR/CI/Ready → explicit MERGE → trusted-checkout convergence → root read-only recovery preflight → separate exact LIVE recovery apply → read-only poststate verification. Only after accepted recovery may a **new** READY queue item and a **new** owner-authored LIVE-AUTH/request ID authorize one new genuine canary. Queue #30 and LIVE-AUTH #9 must never be reused.
