# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE-REGISTERED / PULL-HELPER BOUND / PRIVILEGED DISPATCH SOURCE PRESENT / GLOBALLY EXECUTION-DISABLED / STRICT / NOT HOST-EXECUTABLE**

Tracking:

- current dispatcher source gate: `RPi5_main#361`
- completed helper-binding gate: `RPi5_main#359` / PR #360
- completed privileged-consumer gate: `RPi5_main#356` / PR #357
- completed registry reconciliation: `RPi5_main#352` / PR #353
- completed runner-independent helper source: `hermes-deals#834` / PR #840
- Hermes Deals migration: `rozkalnsandris/hermes-deals#384`
- merged inventory/architecture gate: `hermes-deals#787`
- shared executor roadmap: `RPi5_main#236`

## Current routing

Phase 4 is the residual Hermes Deals origin-audit execution-path migration.

The production operation registry contains `hermes-deals.origin-path-audit.v1` but remains globally `execution_enabled=false`. The operation is:

- authorization class: `STRICT`;
- ordinary LIVE-ALL eligibility: `false`;
- rollback policy: `NONE`;
- invocation budget: exactly one future `hermes-deals.read-only-audit-invocation`;
- adapter behavior: validation-only with fail-closed `apply()`.

Hermes Deals #834 / PR #840 merged the runner-independent capability-specific pull helper. RPi5_main #359 / PR #360 bound the exact reviewed helper provenance/interface and required sanitized host-evidence checks.

RPi5_main #361 adds a **source-only privileged dispatch plan**. It does not switch the production selector, install a broker/helper, invoke an audit, create READY/LIVE-AUTH, mutate a runner, mutate the host, deploy production, write application data, or authorize any later live action.

## Reviewed cross-repository provenance

The #361 source baseline is:

- `rozkalnsandris/hermes-deals/main`: `2f47f64ab15e767f4e53ad182326e64e313d5094`;
- repository ID: `1317143994`;
- origin audit workflow blob: `99a18c5f669e7880a8a8288c3f964285df87ae22`;
- legacy dispatcher blob: `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`;
- legacy installer blob: `41f004420a0f5aed314aaefd796a54e14dbd17ea`;
- probe blob: `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`;
- runner-independent pull helper blob: `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

The pull helper fixes:

- capability `origin-path-audit`;
- registration schema `rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1`;
- evidence schema `rozkalns.hermes-deals.origin-path-rpi5-pull-evidence.v1`;
- machine identity `rpi5`;
- installed helper path `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- caller-visible argument names exactly `registered_source_sha` and `as_of`.

The helper source itself fixes its registration path, probe path, evidence root, execution environment and probe targets. GitHub prose does not select them.

These source identities prove source compatibility only. They do not prove current RPi5 installation, root ownership, permissions, service state, credentials, deployed source, runner state or production health.

## Static selector stays legacy

The source-controlled operation still matches:

- operation: `hermes-deals.origin-path-audit.v1`;
- source repository: `rozkalnsandris/hermes-deals`;
- target alias: `hermes-deals-origin-path-audit`;
- execution location: `trusted-home-host`;
- repository entrypoint: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`;
- baseline resolver: `hermes-deals.origin-path-registration.v1`.

#361 does **not** replace that legacy repository entrypoint. The runner-independent helper is source-bound behind the future privileged boundary, but selector/cutover remains a later separately reviewed gate.

## Identity-only privileged request

The privileged request carries only:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

Any source SHA, `as_of`, capability, operation, target, command, path, argv, environment, sudo target, URL or artifact/evidence path supplied by the caller is rejected as an extra field.

## Mandatory consumer revalidation

`consume_privileged_request()` must independently prove the complete canonical state twice, with sanitized host evidence between the two reads:

1. isolated owner-only authorization surface;
2. exact authorization issue identity;
3. GitHub server-side `authorization_created_at`;
4. owner identity, TTL, body stability and replay eligibility;
5. exact READY queue binding;
6. exact source repository/SHA and merged reachability;
7. exact-SHA CI success;
8. exact operation/adapter/target;
9. `STRICT`, not ordinary LIVE-ALL;
10. globally disabled registry and prepared execution;
11. rollback `NONE` and one-invocation budget;
12. all fixed exclusions and reviewed provenance;
13. baseline match;
14. read-only adapter preflight with live dispatch still not ready.

The two immutable canonical snapshots must compare equal. Drift in the authorization timestamp, TTL, body, replay state, queue, source, CI, operation, policy or provenance prevents readiness.

## Canonical helper parameters

The source SHA is not request authority. `registered_source_sha` is the exact SHA from the fully revalidated canonical evidence and must also match sanitized host registration evidence.

`as_of` is not request authority. It is the UTC calendar date derived from the already validated GitHub server-side owner authorization creation timestamp:

`authorization_created_at -> YYYY-MM-DD`

This derivation is source-fixed. A caller cannot override it.

## Privileged dispatch source boundary

`hermes_deals_origin_privileged_dispatcher.py` accepts only:

- the identity-only request;
- the typed canonical revalidator;
- the typed sanitized host-evidence resolver.

It calls `consume_privileged_request()` and emits one immutable plan that source-binds:

- schema `rozkalns.hermes-deals.origin-privileged-dispatch-plan.v1`;
- operation `hermes-deals.origin-path-audit.v1`;
- capability `origin-path-audit`;
- helper blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- helper installed path `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- argument names exactly `registered_source_sha`, `as_of`;
- argument values only from revalidated canonical evidence.

It does not expose a generic subprocess/shell/sudo interface and does not launch the helper. `PRIVILEGED_DISPATCH_SOURCE_READY` is source readiness only.

## Live flags remain false

The new boundary does not change any live gate:

- `execution_enabled=false`;
- `privileged_dispatch_enabled=false`;
- `host_wiring_enabled=false`;
- `genuine_hermes_audit_authorized=false`;
- `runner_retirement_eligible=false`;
- `production_mutation_started=false`.

`HermesDealsOriginAuditAdapter.apply()` remains fail-closed.

## Legacy runner path

The existing `origin-path-rpi5-audit` workflow and `hermes-deals-audit` self-hosted runner remain unchanged and continue to be the residual execution path until a replacement is separately installed, activated and proven.

The separate `hermes-deals-release` production runner is outside this origin-audit lane.

## Regression contract

Focused tests must prove:

1. the production registry remains globally disabled;
2. the legacy repository entrypoint remains unchanged;
3. the exact helper provenance/capability/schemas/machine/two-argument interface remains bound;
4. the request stays identity-only;
5. caller-supplied SHA/`as_of`/path/argv/env/capability is rejected before revalidation;
6. sanitized host evidence cannot carry path/argv/command authority;
7. canonical authorization timestamp must be exact GitHub UTC RFC3339;
8. canonical timestamp/source/CI/queue/policy drift fails closed across the second revalidation;
9. helper SHA and `as_of` values come only from the canonical consumer result;
10. the dispatcher source contains no process-launch or generic privilege primitive;
11. all dispatch/wiring/live/retirement/production flags remain false.

## Next gates

After #361 reaches Ready, STOP for separate owner MERGE authorization.

After a separately authorized merge, fresh exact-main validation still proves only **source readiness**. Before any live installation there must be another source/security gate that freezes the exact broker/installer/service/permission wiring and cross-repository interface.

Only after that may a separate explicit LIVE authorization install/activate the reviewed host components. A separate later STRICT authorization is required for one genuine read-only audit canary. Runner retirement remains later and separately authorized.
