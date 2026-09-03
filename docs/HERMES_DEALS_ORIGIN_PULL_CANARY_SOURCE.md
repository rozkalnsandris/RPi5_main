# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE-REGISTERED / GLOBALLY EXECUTION-DISABLED / STRICT / NOT HOST-EXECUTABLE**

Tracking:

- current reconciliation: `RPi5_main#352`
- Hermes Deals migration: `rozkalnsandris/hermes-deals#384`
- merged inventory/architecture gate: `hermes-deals#787`
- shared executor roadmap: `RPi5_main#236`
- historical dormant source gate: `RPi5_main#247`
- historical production-registry gate: `RPi5_main#275`
- historical P9 reroute: `RPi5_main#278`

## Current routing

After the ordinary Dashboard P10 canary completed, Phase 4 returned to the residual Hermes Deals execution-path migration. `RPi5_main#352` re-admits the already-reviewed `hermes-deals.origin-path-audit.v1` operation to the source-controlled production operation registry alongside the existing Control Center and Dashboard operations.

This is source reconciliation only. Top-level `execution_enabled=false` remains authoritative. Re-admission does not create READY or LIVE-AUTH state, invoke an audit, install or activate a broker, change a runner, mutate host/runtime state, deploy production, or authorize any later live action.

The operation remains:

- authorization class: `STRICT`;
- ordinary LIVE-ALL eligibility: `false`;
- rollback policy: `NONE`;
- invocation budget: exactly one `hermes-deals.read-only-audit-invocation`;
- adapter behavior: validation-only with fail-closed `apply()`.

## Current cross-repository provenance

Fresh `RPi5_main#352` reconciliation on 2026-09-03 verified the current Hermes Deals source baseline:

- repository: `rozkalnsandris/hermes-deals`;
- stable repository ID: `1317143994`;
- current reviewed `main`: `fbe3cfa143788607446d0095ae1f887354d10eb3`;
- origin audit workflow: `.github/workflows/origin-path-rpi5-audit.yml`;
- workflow source blob: `99a18c5f669e7880a8a8288c3f964285df87ae22`;
- dispatcher: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`;
- dispatcher source blob: `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`;
- installer: `tools/runner/install-origin-path-rpi5-audit.sh`;
- installer source blob: `41f004420a0f5aed314aaefd796a54e14dbd17ea`;
- probe: `tools/hermes_deals_origin_probe.py`;
- probe source blob: `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`.

The static registry and adapter bind all four reviewed workflow/helper blob identities. Missing or mismatched provenance fails closed. These source identities prove reviewed source compatibility only; they do not prove current host installation, root-owned file identity, runner state, credentials, permissions, deployed SHA, runtime configuration, or production health.

Any future executable canary must freshly resolve the authorized Hermes Deals source SHA, merged/reachable state, exact-SHA CI and the then-current reviewed provenance. Historical or current prose must never silently expand authority.

## Static selector and authority boundary

The only reviewed operation identity is `hermes-deals.origin-path-audit.v1` with:

- source repository: `rozkalnsandris/hermes-deals`;
- target alias: `hermes-deals-origin-path-audit`;
- execution location class: `trusted-home-host`;
- repository entrypoint selector: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`;
- baseline resolver: `hermes-deals.origin-path-registration.v1`.

GitHub queue prose is not command, executable path, argv, environment, operation-count or exclusion authority. Normalization must match the exact static selectors in the source registry. An unknown operation or unreviewed entrypoint fails closed.

The fixed exclusions are:

- production database writes;
- production deployment/cutover;
- restart/configuration mutation;
- parser/collector behavior changes;
- runner registration/deregistration;
- GitHub App/credential/permission changes.

The registry may only describe one bounded read-only audit invocation. It does not grant generic shell, sudo, root, process-launch or arbitrary privileged execution authority.

## Privilege boundary

The pull-executor poller remains an unprivileged service identity with `NoNewPrivileges=true` and no generic privileged command bridge.

The reviewed unprivileged-to-privileged request shape remains identity-only: authorization repository identity, authorization issue identity and request UUID. It does not carry source SHA, operation ID, target, command, executable path, argv or mutation budget.

`HermesDealsOriginAuditAdapter` does not cross that boundary. Before any future privileged request could become eligible, a separately reviewed broker/runtime path would have to independently re-fetch and validate LIVE-AUTH, READY queue state, exact source/CI/baseline state, operation registry identity and current host-side registration. This source contract does not assert that such a live boundary is ready.

## Legacy Hermes path

The existing Hermes Deals `origin-path-rpi5-audit` workflow remains unchanged by #352. Its self-hosted `hermes-deals-audit` runner and root-owned dispatcher continue to be residual Phase 4 surfaces until a separately proven replacement and separately authorized retirement exist.

The workflow currently calls the fixed root-owned dispatcher and requires the reviewed workflow/dispatcher/installer/probe source family. Re-admitting the operation to the disabled RPi5 registry does not invoke that workflow and does not modify its runner, dispatcher, installer, probe, sudoers rule, systemd state or source checkout.

The separate `hermes-deals-release` production runner surface is not part of this operation and is not changed or authorized by #352.

## Adapter behavior

`HermesDealsOriginAuditAdapter` is deliberately non-executable:

- preflight verifies exact operation, adapter, repository, SHA shape, target, rollback, invocation budget, exclusions and all reviewed provenance dependencies;
- preflight exposes the four reviewed provenance blob identities as source evidence;
- `execution_enabled` must remain false;
- `apply()` always raises `AdapterError` and performs no launch or mutation;
- postconditions describe only the sanitized evidence fields and required false production-mutation flags;
- the adapter contains no `subprocess`, shell, `sudo`, generic command or process-launch bridge.

## Regression contract

Focused regression coverage proves that:

1. the production registry remains globally `execution_enabled=false`;
2. Control Center and Dashboard operations remain present with their reviewed semantics unchanged;
3. Hermes is re-admitted as `STRICT`, not ordinary LIVE-ALL eligible, with rollback `NONE`;
4. the exact current Hermes source fixture normalizes against the production registry without enabling execution;
5. workflow, dispatcher, installer and probe provenance are bound and missing/drifted provenance fails closed;
6. free-form queue prose cannot expand the static invocation budget or exclusions;
7. an unreviewed entrypoint fails with `UNKNOWN_OPERATION`;
8. adapter preflight remains read-only/disabled and `apply()` remains fail-closed;
9. the privileged dispatch request rejects SHA/operation/command/path/argv authority;
10. source evidence does not claim host/runtime readiness.

## Explicitly not authorized

This source contract does not authorize or perform:

- merge of the #352 source PR without a separate owner decision;
- READY or LIVE-AUTH creation/promotion;
- invoking the Hermes origin-path audit;
- workflow migration or workflow dispatch/rerun;
- executor/broker installation or activation;
- systemd, sudoers, privilege-rule, package, host or runtime mutation;
- source-checkout synchronization on the RPi5;
- runner registration/deregistration or retirement;
- GitHub App, credential, secret or permission changes;
- production deploy/cutover;
- DB/Review/publication writes;
- parser/collector changes;
- Cloudflare/network mutation;
- P11 high-risk/control-plane work.

Source readiness is not live readiness. Any later replacement canary, runner retirement or other host/runtime action requires fresh merged-source validation and its own explicit owner LIVE authorization.
