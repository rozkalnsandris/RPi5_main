# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE-REGISTERED / PULL-HELPER BOUND / BROKER SOURCE MERGED / #365 SOURCE-AUTH + FIXED-LAUNCH PREREQUISITE / GLOBALLY EXECUTION-DISABLED / NOT HOST-EXECUTABLE**

Tracking:

- current source prerequisite: `RPi5_main#365` / Draft PR #366
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
