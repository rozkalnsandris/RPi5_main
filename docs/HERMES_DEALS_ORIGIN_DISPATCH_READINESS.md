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
