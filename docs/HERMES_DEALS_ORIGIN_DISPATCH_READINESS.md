# Hermes Deals origin audit — privileged-consumer source boundary

Status: **SOURCE CONSUMER IMPLEMENTED / NOT MERGED / DISPATCH DISABLED / HOST WIRING DISABLED / RUNNER RETIREMENT NOT ELIGIBLE**

Tracking:

- current work item: `RPi5_main#356`
- completed identity-only request gate: `RPi5_main#354` / PR #355
- completed registry reconciliation: `RPi5_main#352` / PR #353
- Hermes runner migration: `rozkalnsandris/hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Current boundary

PR #353 re-admitted `hermes-deals.origin-path-audit.v1` to the source-controlled operation registry while global `execution_enabled=false` remains authoritative. The operation is `STRICT`, not ordinary LIVE-ALL eligible, has rollback policy `NONE`, and permits at most one future `hermes-deals.read-only-audit-invocation`.

PR #355 then froze an identity-only request carrying only `schema` and `authorization_issue_number`. It did not add a dispatcher, host wiring, result writer or production apply surface.

Issue #356 implements the next source-only layer: a Hermes-specific privileged-consumer validation/orchestration module. The module can derive `PRIVILEGED_CONSUMER_READY` only after independent canonical revalidation and a separately supplied sanitized host-evidence check. It still cannot invoke the root-owned audit helper, call `HermesDealsOriginAuditAdapter.apply()`, consume a live request, write a result, mutate host state or retire a runner.

The persistent `hermes-deals-audit` self-hosted workflow remains the current historical execution path until a later replacement canary proves otherwise.

## Current reviewed Hermes source provenance

At this source gate the reviewed cross-repository baseline remains:

- `rozkalnsandris/hermes-deals/main`: `fbe3cfa143788607446d0095ae1f887354d10eb3`
- workflow `.github/workflows/origin-path-rpi5-audit.yml`: blob `99a18c5f669e7880a8a8288c3f964285df87ae22`
- dispatcher `tools/runner/origin-path-rpi5-audit-dispatcher.sh`: blob `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`
- installer `tools/runner/install-origin-path-rpi5-audit.sh`: blob `41f004420a0f5aed314aaefd796a54e14dbd17ea`
- probe `tools/hermes_deals_origin_probe.py`: blob `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`

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

The consumer receives no source, queue, operation, dispatcher or host path authority from the caller. Those values must be re-derived from reviewed canonical interfaces.

## Independent canonical revalidation

`hermes_deals_origin_privileged_consumer.py` requires a capability-specific read-only canonical revalidator. Before source readiness can be emitted, the returned evidence must prove all of the following:

1. the revalidated LIVE-AUTH issue number exactly equals the identity-only request;
2. request identity, queue issue and source-CI run identity are valid;
3. owner identity, authorization TTL and authorization body stability are freshly valid;
4. the queue is READY;
5. source repository is exactly `rozkalnsandris/hermes-deals`;
6. exact source SHA is merged/reachable and exact-SHA CI succeeded;
7. operation and adapter are exactly `hermes-deals.origin-path-audit.v1`;
8. target alias is exactly `hermes-deals-origin-path-audit`;
9. authorization class is `STRICT` and ordinary LIVE-ALL eligibility is false;
10. global registry and prepared-operation execution remain disabled;
11. rollback remains `NONE` and mutation budget remains exactly one read-only audit invocation;
12. required exclusions and all reviewed source/provenance dependencies remain present;
13. baseline validation passed;
14. adapter preflight is read-only and still reports privileged dispatch not ready.

After sanitized host evidence is resolved, the consumer requires a final `verify_unchanged()` authorization check immediately before emitting its source-only readiness result.

## Sanitized host-evidence contract

The host-evidence resolver is a separately supplied read-only interface. Its output has an exact schema and may contain only:

- schema and public-safe evidence ID;
- exact operation ID;
- registered source SHA;
- fixed registration name;
- booleans proving root ownership, `0600` registration mode, dispatcher/probe/workflow identity match and read-only capture;
- `protected_values_included=false`.

Extra fields fail closed. In particular, raw protected configuration, credential values, arbitrary paths, argv, environment or command authority cannot enter this contract.

This source contract does not itself inspect the host and does not prove any current runtime fact.

## Deliberately absent execution surface

The #356 consumer source has no subprocess/shell execution, no generic sudo bridge, no systemd control, no socket/spool service, no `adapter.apply()` call, no StateStore `consume()`, no result writer and no host mutation API.

`PRIVILEGED_CONSUMER_READY` therefore means only that a future privileged host component could be eligible for a separate installation/activation review. It is not an audit authorization and cannot cause the root-owned Hermes dispatcher to run.

## Gate separation

1. **#352 complete** — Hermes operation source-registered while globally disabled.
2. **#354 complete** — identity-only privileged-boundary request frozen.
3. **#356 current** — capability-specific privileged consumer source implementation and inert validation proof.
4. **Future LIVE host gate** — separately authorize installation/activation of the exact reviewed consumer/broker and any required capability-specific host wiring.
5. **Future STRICT canary gate** — separately authorize exactly one genuine read-only Hermes origin audit and require sanitized postconditions with no production mutation.
6. **Runner retirement gate** — only after the replacement path has one accepted end-to-end canary and current capability coverage is proven; runner deregistration remains a separate LIVE authorization.

The separate `hermes-deals-release` production runner remains outside this lane and is not made retirement-eligible by an origin-audit canary.

## Current classification

`CURRENT_WORK_ITEM=RPi5_main#356`

`CURRENT_PHASE=4`

`GLOBAL_EXECUTION_ENABLED=false`

`P9_DRY_RUN_SOURCE_READY=true`

`PRIVILEGED_CONSUMER_IMPLEMENTED=true`

`PRIVILEGED_DISPATCH_IMPLEMENTED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`HERMES_AUDIT_RUNNER_RETIREMENT_ELIGIBLE=false`

`HERMES_RELEASE_RUNNER_IN_SCOPE=false`

`PRODUCTION_MUTATION_STARTED=false`

Merge of this source gate never changes any live/runtime flag by itself.