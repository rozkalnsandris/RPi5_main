# Hermes Deals origin audit — runner-independent helper binding boundary

Status: **PULL-HELPER BINDING IMPLEMENTED / NOT MERGED / DISPATCH DISABLED / HOST WIRING DISABLED / RUNNER RETIREMENT NOT ELIGIBLE**

Tracking:

- current work item: `RPi5_main#359`
- completed privileged-consumer gate: `RPi5_main#356` / PR #357
- completed identity-only request gate: `RPi5_main#354` / PR #355
- completed registry reconciliation: `RPi5_main#352` / PR #353
- completed Hermes runner-independent helper source: `hermes-deals#834` / PR #840
- Hermes runner migration: `rozkalnsandris/hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Current boundary

PR #353 re-admitted `hermes-deals.origin-path-audit.v1` to the source-controlled operation registry while global `execution_enabled=false` remains authoritative. The operation is `STRICT`, not ordinary LIVE-ALL eligible, has rollback policy `NONE`, and permits at most one future `hermes-deals.read-only-audit-invocation`.

PR #355 froze an identity-only request carrying only `schema` and `authorization_issue_number`. It did not add a dispatcher, host wiring, result writer or production apply surface.

PR #357 added the Hermes-specific privileged-consumer validation/orchestration module. The module can derive `PRIVILEGED_CONSUMER_READY` only after two complete canonical revalidations with fresh sanitized host evidence between them. It still cannot invoke a root-owned audit helper, call `HermesDealsOriginAuditAdapter.apply()`, consume a live request, write a result, mutate host state or retire a runner.

Hermes Deals #834 / PR #840 then added a separate runner-independent, capability-specific pull helper. RPi5_main #359 binds that reviewed helper identity and interface into the inert adapter/consumer source contract. This binding is provenance-only: the production registry's static repository entrypoint remains the legacy dispatcher until a separately reviewed replacement/cutover gate exists.

The persistent `hermes-deals-audit` self-hosted workflow therefore remains the existing execution path until a later replacement canary proves otherwise.

## Current reviewed Hermes source provenance

The reviewed cross-repository source baseline for #359 is:

- `rozkalnsandris/hermes-deals/main`: `2f47f64ab15e767f4e53ad182326e64e313d5094`
- workflow `.github/workflows/origin-path-rpi5-audit.yml`: blob `99a18c5f669e7880a8a8288c3f964285df87ae22`
- legacy dispatcher `tools/runner/origin-path-rpi5-audit-dispatcher.sh`: blob `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`
- legacy installer `tools/runner/install-origin-path-rpi5-audit.sh`: blob `41f004420a0f5aed314aaefd796a54e14dbd17ea`
- probe `tools/hermes_deals_origin_probe.py`: blob `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`
- runner-independent helper `tools/runner/origin_path_rpi5_pull_helper.py`: blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`

The runner-independent helper source fixes:

- capability: `origin-path-audit`;
- registration schema: `rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1`;
- evidence schema: `rozkalns.hermes-deals.origin-path-rpi5-pull-evidence.v1`;
- machine identity: `rpi5`;
- caller-visible arguments: exactly `registered_source_sha` and `as_of`.

Its registration path, installed helper path, probe path and evidence root are source-fixed. The caller cannot select a command, executable path, environment, output path, evidence root, probe path, sudo target or arbitrary argv.

These are source-review anchors only. They do not prove current installed files, ownership, sudoers, runner state, credentials, runtime configuration or production health.

## Identity-only caller authority

The privileged consumer accepts only:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

The request parser rejects every extra field, including command/shell text, executable paths, argv, environment, sudo authority, source SHA, `as_of`, artifact paths and repository entrypoints.

The consumer receives no source, queue, operation, dispatcher, helper or host-path authority from the caller. Those values must be re-derived through capability-specific reviewed interfaces.

## Complete canonical revalidation

`hermes_deals_origin_privileged_consumer.py` requires a capability-specific read-only canonical revalidator. Each complete revalidation must prove:

1. the isolated authorization surface is the reviewed one;
2. the revalidated LIVE-AUTH issue number exactly equals the identity-only request;
3. request identity, queue issue and source-CI run identity are valid;
4. owner identity, authorization TTL and authorization body stability are valid;
5. replay state is available and the request is eligible for this read-only source gate;
6. the queue is READY and its binding to the authorization is valid;
7. source repository is exactly `rozkalnsandris/hermes-deals`;
8. exact source SHA is merged/reachable and exact-SHA CI succeeded;
9. operation and adapter are exactly `hermes-deals.origin-path-audit.v1`;
10. target alias is exactly `hermes-deals-origin-path-audit`;
11. authorization class is `STRICT` and ordinary LIVE-ALL eligibility is false;
12. global registry and prepared-operation execution remain disabled;
13. rollback remains `NONE` and mutation budget remains exactly one read-only audit invocation;
14. required exclusions and all reviewed legacy plus runner-independent helper provenance/interface dependencies remain present;
15. baseline validation passed;
16. adapter preflight is read-only and still reports privileged dispatch not ready.

The consumer performs this full revalidation before host evidence resolution and repeats the full revalidation after host evidence resolution. Both immutable evidence snapshots must be exactly equal. TTL, replay, queue/source/CI/policy drift therefore fails closed before `PRIVILEGED_CONSUMER_READY`.

## Sanitized host-evidence contract

The host-evidence resolver is a separately supplied read-only interface. Its output has an exact schema and may contain only:

- schema and public-safe evidence ID;
- exact operation ID;
- registered source SHA;
- fixed registration name;
- booleans proving root ownership and `0600` registration mode;
- legacy dispatcher/probe/workflow identity-match booleans;
- runner-independent pull-helper identity-match and interface-match booleans;
- `evidence_read_only=true`;
- `evidence_fresh=true`;
- `protected_values_included=false`.

Missing, false or extra helper evidence fails closed. In particular, raw protected configuration, credential values, arbitrary paths, argv, environment or command authority cannot enter this contract.

This source contract does not itself inspect the host and does not prove any current runtime fact.

## Deliberately absent execution surface

The privileged-consumer source has no subprocess/shell execution, no generic sudo bridge, no systemd control, no socket/spool service, no `adapter.apply()` call, no StateStore `consume()`, no result writer and no host mutation API.

#359 also does not select the new runner-independent helper as the production registry entrypoint. It only binds its reviewed provenance and interface so a later source/host gate can fail closed on helper drift.

`PRIVILEGED_CONSUMER_READY` means only that source-level canonical and sanitized-evidence contracts converged. It is not an audit authorization and cannot cause either the legacy dispatcher or the runner-independent pull helper to run.

## Gate separation

1. **#352 complete** — Hermes operation source-registered while globally disabled.
2. **#354 complete** — identity-only privileged-boundary request frozen.
3. **#356 / PR #357 complete** — capability-specific privileged consumer source implementation and inert validation proof.
4. **Hermes #834 / PR #840 complete** — runner-independent capability-specific pull helper source merged.
5. **#359 current** — bind the exact helper provenance/interface into RPi5 source and sanitized host-evidence requirements while leaving execution disabled and the legacy entrypoint unchanged.
6. **Future LIVE host gate** — separately authorize installation/activation of an exact reviewed consumer/broker/helper and any required capability-specific host wiring.
7. **Future STRICT canary gate** — separately authorize exactly one genuine read-only Hermes origin audit and require sanitized postconditions with no production mutation.
8. **Runner retirement gate** — only after the replacement path has one accepted end-to-end canary and current capability coverage is proven; runner deregistration remains a separate LIVE authorization.

The separate `hermes-deals-release` production runner remains outside this lane and is not made retirement-eligible by an origin-audit canary.

## Current classification

`CURRENT_WORK_ITEM=RPi5_main#359`

`CURRENT_PHASE=4`

`GLOBAL_EXECUTION_ENABLED=false`

`P9_DRY_RUN_SOURCE_READY=true`

`PRIVILEGED_CONSUMER_IMPLEMENTED=true`

`RUNNER_INDEPENDENT_PULL_HELPER_SOURCE_BOUND=true`

`PRIVILEGED_DISPATCH_IMPLEMENTED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`HERMES_AUDIT_RUNNER_RETIREMENT_ELIGIBLE=false`

`HERMES_RELEASE_RUNNER_IN_SCOPE=false`

`PRODUCTION_MUTATION_STARTED=false`

Merge of this source gate never changes any live/runtime flag by itself.
