# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE-REGISTERED / PULL-HELPER PROVENANCE BOUND / GLOBALLY EXECUTION-DISABLED / STRICT / NOT HOST-EXECUTABLE**

Tracking:

- current helper-binding gate: `RPi5_main#359`
- completed privileged-consumer gate: `RPi5_main#356` / PR #357
- completed registry reconciliation: `RPi5_main#352` / PR #353
- completed runner-independent helper source: `hermes-deals#834` / PR #840
- Hermes Deals migration: `rozkalnsandris/hermes-deals#384`
- merged inventory/architecture gate: `hermes-deals#787`
- shared executor roadmap: `RPi5_main#236`
- historical dormant source gate: `RPi5_main#247`
- historical production-registry gate: `RPi5_main#275`
- historical P9 reroute: `RPi5_main#278`

## Current routing

After the ordinary Dashboard P10 canary completed, Phase 4 returned to the residual Hermes Deals execution-path migration. `RPi5_main#352` re-admitted the reviewed `hermes-deals.origin-path-audit.v1` operation to the source-controlled production operation registry alongside the existing Control Center and Dashboard operations.

Hermes Deals #834 / PR #840 later merged a separate runner-independent `origin-path-audit` pull helper. `RPi5_main#359` binds that helper's exact reviewed provenance and capability-specific interface into the existing dormant RPi5 operation contract. It does **not** switch the production registry selector away from the legacy dispatcher.

This remains source reconciliation only. Top-level `execution_enabled=false` is authoritative. The binding does not create READY or LIVE-AUTH state, invoke an audit, install or activate a broker/helper, change a runner, mutate host/runtime state, deploy production, or authorize any later live action.

The operation remains:

- authorization class: `STRICT`;
- ordinary LIVE-ALL eligibility: `false`;
- rollback policy: `NONE`;
- invocation budget: exactly one `hermes-deals.read-only-audit-invocation`;
- adapter behavior: validation-only with fail-closed `apply()`.

## Current cross-repository provenance

The #359 reviewed Hermes Deals source baseline is:

- repository: `rozkalnsandris/hermes-deals`;
- stable repository ID: `1317143994`;
- current reviewed `main`: `2f47f64ab15e767f4e53ad182326e64e313d5094`;
- origin audit workflow: `.github/workflows/origin-path-rpi5-audit.yml`;
- workflow source blob: `99a18c5f669e7880a8a8288c3f964285df87ae22`;
- legacy dispatcher: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`;
- dispatcher source blob: `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`;
- legacy installer: `tools/runner/install-origin-path-rpi5-audit.sh`;
- installer source blob: `41f004420a0f5aed314aaefd796a54e14dbd17ea`;
- probe: `tools/hermes_deals_origin_probe.py`;
- probe source blob: `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`;
- runner-independent pull helper: `tools/runner/origin_path_rpi5_pull_helper.py`;
- pull-helper source blob: `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

The static registry and adapter bind the legacy provenance plus the runner-independent pull-helper blob, capability, registration/evidence schemas, machine identity and exact two-argument interface. Missing or mismatched provenance fails closed.

The reviewed pull-helper interface is fixed to:

- capability `origin-path-audit`;
- registration schema `rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1`;
- evidence schema `rozkalns.hermes-deals.origin-path-rpi5-pull-evidence.v1`;
- machine identity `rpi5`;
- caller-visible arguments exactly `registered_source_sha` and `as_of`.

The helper source itself fixes its registration path, installed helper path, probe path and evidence root. The caller does not select command text, an executable path, environment, output path, evidence root, probe path, sudo target or arbitrary argv.

These source identities prove reviewed source compatibility only; they do not prove current host installation, root-owned file identity, runner state, credentials, permissions, deployed SHA, runtime configuration, or production health.

Any future executable canary must freshly resolve the authorized Hermes Deals source SHA, merged/reachable state, exact-SHA CI and the then-current reviewed provenance. Historical or current prose must never silently expand authority.

## Static selector and authority boundary

The only reviewed operation identity remains `hermes-deals.origin-path-audit.v1` with:

- source repository: `rozkalnsandris/hermes-deals`;
- target alias: `hermes-deals-origin-path-audit`;
- execution location class: `trusted-home-host`;
- current repository entrypoint selector: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`;
- baseline resolver: `hermes-deals.origin-path-registration.v1`.

The current repository entrypoint deliberately remains the legacy dispatcher. #359 is a provenance/interface prerequisite, not replacement activation or cutover.

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

The reviewed unprivileged-to-privileged request shape remains identity-only. The Hermes-specific privileged-consumer request carries only `schema` and `authorization_issue_number`; it does not carry source SHA, operation ID, target, command, executable path, argv, environment, `as_of`, output path or mutation budget.

`HermesDealsOriginAuditAdapter` does not cross that boundary. Before any future privileged request could become eligible, the separately reviewed consumer/runtime path must independently re-fetch and validate LIVE-AUTH, READY queue state, exact source/CI/baseline state, operation registry identity and sanitized host-side evidence.

After #359, sanitized host evidence must additionally prove both the runner-independent pull-helper identity and the reviewed pull-helper interface match. Missing, false or extra evidence fails closed. This source contract still does not assert that any live boundary is installed or ready.

## Legacy Hermes path

The existing Hermes Deals `origin-path-rpi5-audit` workflow remains unchanged by #359. Its self-hosted `hermes-deals-audit` runner and root-owned dispatcher continue to be residual Phase 4 surfaces until a separately proven replacement and separately authorized retirement exist.

The workflow currently calls the fixed root-owned dispatcher and requires the reviewed workflow/dispatcher/installer/probe source family. Binding the new runner-independent helper in the disabled RPi5 source contract does not invoke that workflow and does not modify its runner, dispatcher, installer, probe, sudoers rule, systemd state or source checkout.

The separate `hermes-deals-release` production runner surface is not part of this operation and is not changed or authorized by #359.

## Adapter behavior

`HermesDealsOriginAuditAdapter` is deliberately non-executable:

- preflight verifies exact operation, adapter, repository, SHA shape, target, rollback, invocation budget, exclusions and all reviewed provenance dependencies;
- preflight exposes legacy blob identities plus the exact runner-independent pull-helper source/interface contract as source evidence;
- `execution_enabled` must remain false;
- `privileged_dispatch_ready` remains false;
- `apply()` always raises `AdapterError` and performs no launch or mutation;
- postconditions describe only sanitized evidence fields and required false production-mutation flags;
- the adapter contains no `subprocess`, shell, `sudo`, generic command or process-launch bridge.

## Regression contract

Focused regression coverage proves that:

1. the production registry remains globally `execution_enabled=false`;
2. Control Center and Dashboard operations remain present with their reviewed semantics unchanged;
3. Hermes remains `STRICT`, not ordinary LIVE-ALL eligible, with rollback `NONE`;
4. the exact Hermes queue fixture normalizes against the production registry without enabling execution;
5. legacy workflow/dispatcher/installer/probe provenance remains bound;
6. the exact runner-independent pull-helper blob/capability/schemas/machine identity/two-argument interface is bound and missing/drifted provenance fails closed;
7. sanitized host evidence must prove the pull-helper identity and interface match;
8. free-form queue/request prose cannot expand command/path/argv/environment/output authority or the static invocation budget;
9. the legacy repository entrypoint remains unchanged by this source gate;
10. adapter preflight remains read-only/disabled and `apply()` remains fail-closed;
11. source evidence does not claim host/runtime readiness or audit authorization.

## Explicitly not authorized

This source contract does not authorize or perform:

- merge of the #359 source PR without a separate owner decision;
- READY or LIVE-AUTH creation/promotion;
- invoking either Hermes origin-path helper;
- workflow migration or workflow dispatch/rerun;
- executor/broker/helper installation or activation;
- systemd, sudoers, privilege-rule, package, host or runtime mutation;
- source-checkout synchronization on the RPi5;
- runner registration/deregistration or retirement;
- GitHub App, credential, secret or permission changes;
- production deploy/cutover;
- DB/Review/publication writes;
- parser/collector changes;
- Cloudflare/network mutation;
- P11 high-risk/control-plane work.

Source readiness is not live readiness. Any later helper installation, replacement canary, runner retirement or other host/runtime action requires fresh merged-source validation and its own explicit owner LIVE authorization.
