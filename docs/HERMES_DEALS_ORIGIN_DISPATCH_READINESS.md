# Hermes Deals origin audit — privileged dispatcher source boundary

Status: **PRIVILEGED DISPATCH SOURCE IMPLEMENTED / NOT MERGED / DISPATCH DISABLED / HOST WIRING DISABLED / RUNNER RETIREMENT NOT ELIGIBLE**

Tracking:

- current work item: `RPi5_main#361`
- completed pull-helper binding: `RPi5_main#359` / PR #360
- completed privileged-consumer gate: `RPi5_main#356` / PR #357
- completed identity-only request gate: `RPi5_main#354` / PR #355
- completed registry reconciliation: `RPi5_main#352` / PR #353
- completed Hermes runner-independent helper source: `hermes-deals#834` / PR #840
- Hermes runner migration: `rozkalnsandris/hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Current boundary

PR #353 source-registered `hermes-deals.origin-path-audit.v1` while the production registry remains globally `execution_enabled=false`. The operation is `STRICT`, not ordinary LIVE-ALL eligible, has rollback policy `NONE`, and permits at most one future `hermes-deals.read-only-audit-invocation`.

PR #355 froze an identity-only request carrying only `schema` and `authorization_issue_number`.

PR #357 added the capability-specific privileged consumer. It emits `PRIVILEGED_CONSUMER_READY` only after a complete canonical revalidation, fresh sanitized host-evidence resolution, and a second complete canonical revalidation whose immutable evidence must exactly equal the first.

Hermes Deals #834 / PR #840 added the runner-independent `origin-path-audit` pull helper. RPi5_main #359 / PR #360 bound that helper's reviewed source identity, capability, schemas, machine identity and two-argument interface into the dormant RPi5 contract.

#361 adds the next source-only boundary: `hermes_deals_origin_privileged_dispatcher.py`. It converts the fully revalidated consumer result into one immutable capability-specific **dispatch plan**. It does not execute the plan, launch a process, call `sudo`, invoke `adapter.apply()`, install a helper, wire a service, or mutate host/runtime state.

The production registry selector deliberately remains the legacy `tools/runner/origin-path-rpi5-audit-dispatcher.sh`. This issue does not perform replacement cutover.

## Reviewed Hermes source provenance

Current source baseline for #361:

- `rozkalnsandris/RPi5_main/main`: `68a6246171af014dac79711ebc510ddbc6c3d31a` at activation;
- `rozkalnsandris/hermes-deals/main`: `2f47f64ab15e767f4e53ad182326e64e313d5094`;
- workflow `.github/workflows/origin-path-rpi5-audit.yml`: blob `99a18c5f669e7880a8a8288c3f964285df87ae22`;
- legacy dispatcher `tools/runner/origin-path-rpi5-audit-dispatcher.sh`: blob `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`;
- legacy installer `tools/runner/install-origin-path-rpi5-audit.sh`: blob `41f004420a0f5aed314aaefd796a54e14dbd17ea`;
- probe `tools/hermes_deals_origin_probe.py`: blob `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`;
- runner-independent helper `tools/runner/origin_path_rpi5_pull_helper.py`: blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

The runner-independent helper source fixes:

- capability: `origin-path-audit`;
- registration schema: `rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1`;
- evidence schema: `rozkalns.hermes-deals.origin-path-rpi5-pull-evidence.v1`;
- machine identity: `rpi5`;
- installed helper path: `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- caller-visible argument names: exactly `registered_source_sha` and `as_of`.

These are source-review anchors only. They prove no current installed files, ownership, sudoers, credentials, service state, runner state, runtime configuration or production health.

## Identity-only caller authority

The only accepted request remains:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

Every extra field fails closed. In particular the caller cannot provide source SHA, `as_of`, capability, command, shell, executable/helper path, argv, environment, sudo target, URL, artifact directory, evidence path or machine identity.

## Canonical source SHA and `as_of`

`CanonicalHermesOriginEvidence` now includes the GitHub server-side owner authorization creation timestamp as `authorization_created_at`.

The consumer requires that value in canonical GitHub UTC RFC3339 form:

`YYYY-MM-DDTHH:MM:SSZ`

The complete canonical evidence, including this timestamp and the exact source SHA, is revalidated both before and after sanitized host evidence. Any change in timestamp, TTL, body, replay state, queue, source, CI, baseline, operation, provenance or policy fails closed before a dispatch plan can exist.

The helper's `as_of` is not caller authority. It is deterministically derived as the UTC calendar date of the already validated `authorization_created_at` value. For example:

`2026-09-04T07:26:48Z -> 2026-09-04`

The source SHA used as `registered_source_sha` is the exact revalidated canonical source SHA, and sanitized host evidence must already bind the registered source SHA to that same value.

## Capability-specific dispatch plan

`prepare_hermes_deals_origin_privileged_dispatch()`:

1. accepts only the identity-only request plus typed read-only revalidator/resolver interfaces;
2. calls `consume_privileged_request()`;
3. consumes only its immutable `PRIVILEGED_CONSUMER_READY` result;
4. binds capability exactly `origin-path-audit`;
5. binds helper blob exactly `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
6. binds installed helper path exactly `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
7. binds argument names exactly `registered_source_sha`, `as_of`;
8. supplies argument values only from the canonical consumer result;
9. emits `PRIVILEGED_DISPATCH_SOURCE_READY` while every live/runtime flag remains false.

There is no configurable capability selector, executable selector, path selector, argv extender, environment selector, shell command, generic subprocess invoker or generic sudo bridge.

The dispatch plan is source data only. No code in this gate launches the reviewed helper.

## Sanitized host-evidence contract

Host evidence remains exact-schema, read-only and public-safe. It may contain only the reviewed evidence ID, operation/source identity and fixed boolean identity checks. It may not contain raw protected configuration, credentials, arbitrary helper/dispatcher paths, argv, environment or command authority.

Missing, false or extra fields fail closed. The source contract itself does not inspect the live host.

## Legacy path and registry remain unchanged

The production registry remains globally `execution_enabled=false` and continues to select:

`tools/runner/origin-path-rpi5-audit-dispatcher.sh`

The existing self-hosted `hermes-deals-audit` workflow therefore remains the current execution path until a separately reviewed replacement/cutover and accepted end-to-end canary exist.

The separate `hermes-deals-release` production runner remains outside this lane.

## Gate separation

1. **#352 complete** — operation source-registered while globally disabled.
2. **#354 / PR #355 complete** — identity-only privileged-boundary request.
3. **#356 / PR #357 complete** — double-revalidation privileged consumer, still non-executable.
4. **Hermes #834 / PR #840 complete** — runner-independent capability-specific pull-helper source.
5. **#359 / PR #360 complete** — helper provenance/interface and sanitized host-evidence binding.
6. **#361 current** — capability-specific privileged dispatcher **source plan** with canonical source SHA and `as_of`; no execution.
7. **Future source/host installation-wiring security gate** — prove exact installer/broker/service/permission boundary and source compatibility before any host mutation.
8. **Future LIVE host gate** — separate explicit owner authorization to install/activate only the exact reviewed capability-specific components and wiring.
9. **Future STRICT canary gate** — separate explicit authorization for one genuine read-only Hermes origin audit with sanitized postconditions.
10. **Runner retirement gate** — only after accepted replacement canary and proven capability coverage; deregistration remains separate LIVE authorization.

A source merge at gate 6 never authorizes gates 7-10.

## Current classification

`CURRENT_WORK_ITEM=RPi5_main#361`

`CURRENT_PHASE=4`

`GLOBAL_EXECUTION_ENABLED=false`

`P9_DRY_RUN_SOURCE_READY=true`

`PRIVILEGED_CONSUMER_IMPLEMENTED=true`

`RUNNER_INDEPENDENT_PULL_HELPER_SOURCE_BOUND=true`

`PRIVILEGED_DISPATCH_IMPLEMENTED=true`

`PRIVILEGED_DISPATCH_ENABLED=false`

`PROCESS_LAUNCH_SURFACE=false`

`HOST_WIRING_ENABLED=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`HERMES_AUDIT_RUNNER_RETIREMENT_ELIGIBLE=false`

`HERMES_RELEASE_RUNNER_IN_SCOPE=false`

`PRODUCTION_MUTATION_STARTED=false`
