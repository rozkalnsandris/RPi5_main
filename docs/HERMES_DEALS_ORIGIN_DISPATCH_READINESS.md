# Hermes Deals origin audit — privileged dispatcher and broker source boundary

Status: **#366 MERGED / CANONICAL SOURCE-INTEGRATION DRAFT / BROKER ENTRYPOINT INERT / NOT LIVE-INSTALL ELIGIBLE**

Tracking:

- completed prerequisite: `RPi5_main#365` / merged PR #366 at `13c0c46e9966b0682b53553a92bed510cf491c86`
- current work item: unmerged Hermes canonical source-integration draft
- completed broker installation/wiring source gate: `RPi5_main#363` / PR #364
- completed privileged-dispatch plan: `RPi5_main#361` / PR #362
- completed pull-helper binding: `RPi5_main#359` / PR #360
- completed privileged-consumer gate: `RPi5_main#356` / PR #357
- completed identity-only request gate: `RPi5_main#354` / PR #355
- completed registry reconciliation: `RPi5_main#352` / PR #353
- runner-independent helper source: `hermes-deals#834` / PR #840
- Hermes runner migration: `rozkalnsandris/hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Current source baseline

At #365 creation:

- `RPi5_main/main = 9c60248547043ee5ae7b1d0e2897fd9b8aac381a`;
- exact-main Validate #820, FAST-LANE #276 and GITHUB-ONLY #264 are SUCCESS;
- `hermes-deals/main = 511c1566111983f809bc958bc4b68510771d3efb`;
- that Hermes head is a verified docs-only bot commit whose parent is the prior reviewed source checkpoint `2f47f64ab15e767f4e53ad182326e64e313d5094`;
- runner-independent helper blob remains exactly `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673` on current Hermes main;
- Hermes Deals repository ID is `1317143994`.

The current Hermes head had no commit-associated workflow runs returned by the GitHub connector. This document therefore does **not** claim current-head Hermes CI from historical runs; the unchanged helper blob is the reviewed cross-repository helper identity for this gate.

These values are source-review anchors only. They prove no current RPi5 files, ownership, permissions, credentials, App installation selection, units, sockets, runner state or runtime health.

## Completed #363/#364 broker boundary

PR #364 merged the source contract for the dedicated identity-only UNIX socket broker. The caller still supplies only:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

The broker calls `prepare_hermes_deals_origin_privileged_dispatch()` itself, preserving the mandatory double canonical revalidation and sanitized host-evidence check before an immutable helper plan exists. Caller-supplied source SHA, `as_of`, helper path, arbitrary argv/env, UID/GID, unit, capability, URL, command or output path remains forbidden.

The source-only transport remains fixed to:

- socket `rozkalns-hermes-deals-origin-broker.socket`;
- `/run/rozkalns-hermes-deals-origin-broker/request.sock`;
- `root:rozkalns-deploy-executor` mode `0660`;
- `Accept=yes`, `MaxConnections=1`;
- per-connection root service `rozkalns-hermes-deals-origin-broker@.service`;
- broker path `/usr/local/libexec/rozkalns-hermes-deals-origin-broker`.

The existing unprivileged poller retains `NoNewPrivileges=true` and no generic sudo/root/Docker-socket authority. The generic `ops/bin/rozkalns-deploy-dispatch` remains `DISABLED`.

## #365 exact read-only source-App composition

The existing `p9_source_auth.py` provider already enforces source App ID `4537106`, installation ID `152422751`, owner identity, selected-repository installation posture, one-repository installation tokens, short token lifetime and exactly `Actions:read + Contents:read` with metadata read tolerated only as GitHub installation metadata.

#365 adds the exact Hermes repository binding:

- repository `rozkalnsandris/hermes-deals`;
- repository ID `1317143994`;
- requested token permissions exactly `actions:read`, `contents:read`;
- token repository count exactly one.

`hermes_deals_origin_source_auth.py` exposes a Hermes-specific factory with no caller repository/permission selector. This is **source composition**, not runtime proof. No App installation, repository selection, permission or private-key/credential is changed in #365.

Current source classification:

`SOURCE_AUTH_COMPOSITION_IMPLEMENTED=true`

`SOURCE_READ_AUTHORITY_PROVEN=false`

`SOURCE_RUNTIME_CREDENTIAL_PROVEN=false`

`SOURCE_RUNTIME_INSTALLATION_PROVEN=false`

## #365 fixed one-shot helper launch surface

`hermes_deals_origin_helper_launch.py` implements the reviewed fixed process boundary without wiring it to the broker entrypoint.

It can only prepare a launch by calling the existing `prepare_hermes_deals_origin_privileged_dispatch()` path, so the identity-only request must pass the canonical double revalidation immediately before invocation. The socket caller cannot submit a dispatch plan.

The process boundary is source-fixed to:

- executable `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- argv exactly `(registered_source_sha, canonical_as_of)` after the executable;
- helper blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- `shell=False`;
- fixed environment only;
- 50-second timeout;
- stdout/stderr source limits of 4096 bytes each;
- one invocation per launcher instance;
- accepted helper exit codes only `0`, `1`, `2`;
- exact validated stdout identity and false production-mutation flags.

The real helper is never executed by CI; tests inject a fake runner and verify the exact argv/env/timeout/output contract and failure modes.

Current source classification:

`HELPER_PROCESS_LAUNCH_IMPLEMENTED=true`

`HELPER_PROCESS_LAUNCH_WIRED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

## Demand-driven prerequisite discovered during #365

`CanonicalHermesOriginRevalidator` and `SanitizedHermesOriginHostEvidenceResolver` are currently Protocol/test seams. There is no concrete production Hermes composition in `ops/lib/deploy_executor` that reconstructs the complete queue/LIVE-AUTH/source/CI canonical evidence and resolves the sanitized host evidence for the broker.

That means #365 must **not** wire the broker entrypoint to real helper execution and must not claim that LIVE is next merely because token composition and a fixed launcher exist.

After #365 is separately merged and exact-main CI is fresh, a new source integration gate must:

1. implement/review the concrete canonical Hermes revalidator using the already reviewed isolated authorization, queue, registry, source and CI trust contracts;
2. implement/review the concrete sanitized host-evidence resolver without creating caller authority;
3. bind those exact components to the broker entrypoint;
4. preserve the identity-only socket request and fixed helper launcher;
5. keep host/runtime state unchanged until a later separate LIVE authorization.

Only after that integration source gate is merged, exact-main/cross-repository evidence is fresh, and a read-only runtime preflight proves the expected App installation/credential/helper/unit identities may a separate LIVE host-install/activation authorization be considered.

## Installation manifest

`ops/deploy/hermes-deals-origin-broker-installation.json` now records #365 as the source gate. It includes the fixed source-auth repository/App/permission contract and fixed helper-launch contract, but deliberately retains:

- `eligible_source_sha = null`;
- `eligible_source_sha_status = POST_MERGE_EXACT_MAIN_BIND_REQUIRED`;
- `live_install_eligible = false`;
- runtime credential/install proof = false;
- concrete canonical revalidator implemented = false;
- helper launch wired = false.

It remains evidence, not an installer or LIVE authorization.

## Required false flags

- production registry `execution_enabled=false`;
- adapter `apply()` remains fail-closed;
- generic dispatcher remains disabled;
- `privileged_dispatch_enabled=false`;
- `host_wiring_enabled=false`;
- `live_install_eligible=false`;
- `genuine_hermes_audit_authorized=false`;
- `runner_retirement_eligible=false`;
- `production_mutation_started=false`.

## Gate sequence

1. #352 complete — dormant operation registration.
2. #354/#355 complete — identity-only request.
3. #356/#357 complete — double canonical revalidation consumer contract.
4. Hermes #834/#840 complete — runner-independent capability helper.
5. #359/#360 complete — helper provenance/interface + host-evidence binding.
6. #361/#362 complete — immutable capability-specific dispatcher plan.
7. #363/#364 complete — broker/socket/service/install-security source contract.
8. **#365 / PR #366 current** — exact Hermes source-App token composition + fixed one-shot helper launch source, still unwired.
9. **Next source integration gate** — concrete canonical revalidator + host-evidence resolver + broker-entrypoint composition.
10. Fresh exact-main/cross-repository and read-only runtime preflight.
11. Separate explicit LIVE host installation/activation only if all source/runtime prerequisites pass.
12. Separate STRICT authorization for exactly one genuine read-only origin audit canary.
13. Separate LIVE runner retirement only after accepted replacement proof.

## Current classification

`CURRENT_WORK_ITEM=RPi5_main#365`

`CURRENT_PHASE=4`

`GLOBAL_EXECUTION_ENABLED=false`

`PRIVILEGED_CONSUMER_CONTRACT_IMPLEMENTED=true`

`RUNNER_INDEPENDENT_PULL_HELPER_SOURCE_BOUND=true`

`PRIVILEGED_DISPATCH_PLAN_IMPLEMENTED=true`

`BROKER_BOUNDARY_IMPLEMENTED=true`

`SOURCE_AUTH_COMPOSITION_IMPLEMENTED=true`

`SOURCE_READ_AUTHORITY_PROVEN=false`

`CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=false`

`HELPER_PROCESS_LAUNCH_IMPLEMENTED=true`

`HELPER_PROCESS_LAUNCH_WIRED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`LIVE_INSTALL_ELIGIBLE=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`HERMES_AUDIT_RUNNER_RETIREMENT_ELIGIBLE=false`

`HERMES_RELEASE_RUNNER_IN_SCOPE=false`

`PRODUCTION_MUTATION_STARTED=false`

## Source-integration supersession after merged #365/#366 (2026-09-04)

This section supersedes the earlier “current” and “next gate” wording. GitHub freshly reports PR #366 merged as `13c0c46e9966b0682b53553a92bed510cf491c86`; the refreshed local `main` matches. Hermes `main` remains `511c1566111983f809bc958bc4b68510771d3efb`, with the reviewed pull-helper blob still `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

The current unmerged source integration implements:

- a concrete canonical Hermes revalidator using only the reviewed isolated authorization/queue clients and the fixed single-repository Hermes Source App client;
- a sanitized host-evidence resolver whose provider has zero arguments and whose only output is the minimal evidence already consumed by the double-revalidation boundary;
- an inert broker composition binding those exact components to the fixed one-shot helper launcher with a required fake runner seam in CI.

Caller authority remains exactly `authorization_issue_number`. The concrete revalidator accepts no repository, SHA, `as_of`, URL, App, installation, permission, path, command, argv, environment, unit, UID/GID or capability selector.

### Sanitized host observation fields

| Fields | Why necessary |
|---|---|
| `schema`, `evidence_id`, `observed_at` | Version, correlate and freshness-check exactly one bounded observation against GitHub server time. |
| `operation_id`, `registered_source_sha` | Bind host evidence to the canonical Hermes authorization rather than caller prose. |
| Registration path/name/owner/group/mode | Prove the fixed root-owned `0600` registration identity. |
| Broker path/owner/group/mode and socket/service identities | Prove only the reviewed capability-specific privileged boundary. |
| Credential path/owner/group/mode | Prove public location metadata without reading or returning credential content. |
| Pull-helper path/owner/group/mode/blob and argument names | Prove the exact helper and its two canonical arguments. |
| Probe path/blob plus dispatcher/workflow blobs | Bind the complete reviewed origin-audit source chain. |
| Read-only and negative credential/secret/filesystem/systemd/authority/production flags | Fail closed if observation collection expands authority or performs a mutation. |

The raw observation has an exact schema, an 8192-byte ceiling, duplicate-key rejection and a five-minute maximum age. It returns no credential value and exposes no generic path, command or host-inspection API.

Repository source still does **not** prove the actual App installation, credential, replay store, registration, helper, broker, socket or service state. The installed entrypoint remains inert and prints `SOURCE_AUTHORITY_UNPROVEN`; it does not construct the composition or launch a helper.

`CURRENT_WORK_ITEM=HERMES_CANONICAL_SOURCE_INTEGRATION_DRAFT`

`CURRENT_PHASE=4`

`GLOBAL_EXECUTION_ENABLED=false`

`SOURCE_AUTH_COMPOSITION_IMPLEMENTED=true`

`SOURCE_READ_AUTHORITY_PROVEN=false`

`CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=true`

`SANITIZED_HOST_EVIDENCE_RESOLVER_IMPLEMENTED=true`

`BROKER_COMPOSITION_IMPLEMENTED=true`

`BROKER_ENTRYPOINT_WIRED=false`

`HELPER_PROCESS_LAUNCH_IMPLEMENTED=true`

`HELPER_PROCESS_LAUNCH_WIRED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`LIVE_INSTALL_ELIGIBLE=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`RUNNER_RETIREMENT_ELIGIBLE=false`

`PRODUCTION_MUTATION_STARTED=false`

Next sequence: source-integration review/Draft PR → separate MERGE → fresh merged-source and cross-repository validation → read-only runtime preflight → separate LIVE installation authorization → later separate STRICT one-canary authorization → later separate runner-retirement authorization.

## Post-#368 merged-source supersession (2026-09-04)

PR #368 is merged and current `RPi5_main/main` is `2550e77f6cb811ca6f10b49ef0b2fef554d64869`. Exact-main Validate #833, FAST-LANE #289 and GITHUB-ONLY #277 are successful. Hermes remains `511c1566111983f809bc958bc4b68510771d3efb` and the reviewed helper blob remains `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

`CURRENT_WORK_ITEM=HERMES_RUNTIME_PREFLIGHT_PREPARATION`
`ELIGIBLE_SOURCE_SHA=2550e77f6cb811ca6f10b49ef0b2fef554d64869`
`SOURCE_INTEGRATION_MERGED=true`
`SOURCE_READ_AUTHORITY_PROVEN=false`
`BROKER_ENTRYPOINT_WIRED=false`
`HELPER_PROCESS_LAUNCH_WIRED=false`
`HOST_WIRING_ENABLED=false`
`LIVE_INSTALL_ELIGIBLE=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

The next gate is a separate read-only runtime preflight for only the bounded expected App-installation/credential metadata, durable replay adapter, sanitized host-observation adapter, registration, helper, broker, socket and service identities. This merged-source binding itself makes no runtime claim and authorizes no LIVE action.

## Post-first-install local runtime prerequisite preflight supersession (2026-09-05)

The broker transport is now historical PASS evidence from the separately authorized first-install, but installation does not enable dispatch. Source review confirms that the installed entrypoint remains inert, the replay availability and host-observation production providers remain unimplemented Protocol seams, and current Source App installation scope cannot be cryptographically proven without using the protected private key.

`preflight-hermes-deals-origin-runtime-prerequisites.py` therefore implements only the non-mutating local half of runtime readiness. It validates credential metadata without reading credential content, the existing P9 replay database through immutable read-only SQLite access, registration/helper/probe identities, exact broker/shared-prerequisite blobs, the evidence root, and socket enabled/active/listening state. It never mints a token, sends a GitHub request, sends a broker socket request, launches the helper or mutates systemd/filesystem state.

Success is intentionally `HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY`. The Source App scope, concrete replay adapter, concrete host-observation adapter, broker-entrypoint wiring, privileged dispatch and genuine audit authorization remain false. After merge and exact-source convergence, this local preflight may be executed once read-only; only a partial-ready result may advance to a separately reviewed source/trust-boundary decision for protected credential use and production adapter/wiring work.

## Pull-helper prerequisite first-install supersession (2026-09-05)

The first merged local-runtime preflight did not reach `PARTIAL_READY`; it failed closed on the absent runner-independent registration. Focused read-only follow-up established that the helper, probe, registration, evidence root and fixed `rpi5` evidence directory were all absent. No mutation or protected credential content access occurred.

This is the deferred installation slice required by Hermes Deals #834 / PR #840. The new RPi5 first-install operator binds the exact reviewed Hermes PR #840 merge `2f47f64ab15e767f4e53ad182326e64e313d5094`, helper blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`, probe blob `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`, and canonical root-owned registration. It owns only four new `0700` evidence-path directories and three exact files; shared parents remain read-only. Existing owned targets fail closed. The legacy self-hosted-runner installer is explicitly not a replacement path.

The Hermes source checkout is fixed to `<RPi5-checkout-parent>/hermes-deals-origin-pull-trusted` and is not caller-selectable. Preparing that detached clean checkout is a separate LIVE Git mutation and is never performed by the root installer. Installer default mode remains read-only; `--apply` requires its own explicit LIVE owner gate and contains no systemd, credential, socket, helper/audit, deploy, runner or production-data authority.

The runtime prerequisite preflight now also requires the fixed `/var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5` machine directory, matching the #834 helper contract. After this source gate, the exact order is MERGE → source/checkouts convergence → helper installer preflight → separately authorized first-install → fresh runtime prerequisite preflight. Only a future `HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY` can advance to the still-separate Source App scope and production-adapter/wiring design.

## PARTIAL_READY runtime-adapter trust-boundary supersession (2026-09-06)

The owner-controlled root preflight on exact `RPi5_main=e949f7835898fc207aa137cb26ffb6dfc701a497` has now returned `HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY`. Local credential metadata, replay-store structure and installed broker/helper/registration identities are proven read-only, but Source App installation scope, the concrete replay/host-observation runtime adapters, broker entrypoint wiring and privileged dispatch remain separate.

This source gate implements the missing concrete adapters without enabling the broker. `ConcreteDurableHermesOriginReplayAuthority` keeps canonical availability checks immutable/read-only and defines a separate one-shot consume boundary only after double identical canonical revalidation. `ConcreteLocalHermesOriginHostObservationProvider` has no caller arguments and emits the already-reviewed sanitized host-observation schema from fixed identities without reading credential content or invoking systemd/helper/socket requests. Neither adapter is wired to the installed broker entrypoint here.

Current Source App scope proof is explicitly protected rather than disguised as metadata-only validation. The fixed proof path uses App `4537106`, installation `152422751`, only repository `rozkalnsandris/hermes-deals` / id `1317143994`, selected-repository posture, and only `actions:read` + `contents:read`. It signs with the fixed protected key and mints one short-lived installation token solely to validate exact scope; the token is never returned or logged. Runtime use of `--prove` therefore requires a separate explicit LIVE owner authorization.

The post-merge sequence is: exact merged source/trusted checkout → root read-only `HERMES_ORIGIN_RUNTIME_ADAPTERS_READY` preflight → separate LIVE protected Source App `HERMES_SOURCE_APP_SCOPE_PROVEN` proof → only then a new source decision for broker-entrypoint wiring. `BROKER_ENTRYPOINT_WIRED=false`, `PRIVILEGED_DISPATCH_ENABLED=false`, `GENUINE_HERMES_AUDIT_AUTHORIZED=false`, `RUNNER_RETIREMENT_ELIGIBLE=false`, and `PRODUCTION_MUTATION_STARTED=false` remain authoritative in this gate.

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
