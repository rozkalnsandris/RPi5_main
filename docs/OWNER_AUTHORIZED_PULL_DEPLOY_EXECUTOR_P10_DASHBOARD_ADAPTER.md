# P10 Dashboard executor adapter — source-only contract

Status: **source only / execution disabled**.

This document records the source contract created after the first hardened-controller bootstrap and ordinary production PLAN reconciliation. It does not authorize merge, queue READY, LIVE-AUTH, root execution, candidate staging, production APPLY, service/runtime mutation, cleanup or rollback.

## Accepted reconciliation point

The accepted Dashboard candidate `5f7739348f56398d0ba301c9320e1de0062838fc` is already the verified current production release. Its ordinary trusted-controller PLAN returned:

```json
{"status":"PLAN","action":"activate","sourceSha":"5f7739348f56398d0ba301c9320e1de0062838fc","candidateSha256":"c5a2adef8f7242833094a1c0cb8a8074392312567deeddd1228dc46c16cff5c0","observedCurrent":"5f7739348f56398d0ba301c9320e1de0062838fc","targetRelease":"verified-existing","operations":[]}
```

`operations=[]` is a valid proof that the production filesystem already matches that candidate. It is **not** a first-live mutation canary. Do not create a dummy commit, placeholder release, synthetic production delta or artificial filesystem change to manufacture a P10 mutation.

`ops-workflows#28` therefore remains WAITING. A future P10 first-live mutation canary requires a genuine ordinary deployable Dashboard source delta.

## Static operation

The dormant registry operation is:

```text
dashboard-rpi5.production-release.v1
```

Static selectors:

- source repository: `rozkalnsandris/dashboard_RPi5`;
- target alias: `dashboard-rpi5-production-release`;
- execution location class: `trusted-home-host`;
- repository entrypoint selector: `tools/production-release-controller.mjs`;
- deploy class: `AUTO_DEPLOY_SAFE`;
- rollback policy: `NONE`.

GitHub supplies only the reviewed queue data that must match those selectors. It does not supply an executable path, shell command, arbitrary argv, environment injection, destination root or generic sudo authority.

The global executor registry remains:

```json
{"execution_enabled": false}
```

Adding the operation to source does not make it runnable.

## Exact PLAN baseline binding

A future READY queue for this operation must carry the exact values from a separately accepted trusted-controller PLAN in this canonical machine token:

```text
current=<40-lowercase-hex>;candidate=<64-lowercase-hex>
```

`current=none` is syntactically supported by normalization for completeness, but the Dashboard adapter requires an existing reviewed current controller before it can derive a privileged controller path.

The normalized LIVE-AUTH baseline kind is fixed to:

```text
dashboard-release-plan.v1
```

The exact PLAN token is included in the normalized queue and therefore in the queue/LIVE-AUTH equality and body-hash/replay binding. A changed current SHA or candidate digest is a different authorization envelope.

If the PLAN current SHA equals the queued source SHA, normalization fails closed with `QUEUE_NOOP_ALREADY_CURRENT`. That candidate cannot satisfy the P10 first-live mutation canary.

## Capability-specific privileged paths

For a future genuine source SHA `<source>` and reviewed current SHA `<current>`, the dormant adapter derives these paths from source-controlled constants only:

```text
trusted controller:
  /opt/dashboard_RPi5/releases/<current>/tools/production-release-controller.mjs

candidate root:
  /var/lib/rozkalns-dashboard-release-candidates/<source>/source

candidate manifest:
  /var/lib/rozkalns-dashboard-release-candidates/<source>/candidate-manifest.json
```

The future normal candidate staging namespace is intentionally separate from the one-shot bootstrap staging namespace. This source change does not create or populate it. Any future root-owned staging materialization is a separate LIVE gate.

The reviewed APPLY argument shape is derived entirely from those fixed paths plus the exact normalized source/PLAN values:

```text
/usr/bin/node <exact-current-release-controller>
  --candidate-root <fixed-source-derived-candidate-root>
  --manifest <fixed-source-derived-manifest>
  --sha <exact-source-sha>
  --expected-current <exact-plan-current>
  --expected-candidate <exact-plan-candidate-sha256>
  --apply
  --ack I_AUTHORIZED_DASHBOARD_RPI5_PRODUCTION_RELEASE_ACTIVATION
```

The source adapter only constructs and validates this deterministic contract. Its `apply()` remains fail-closed and raises until a later separately reviewed live enablement/installation gate exists.

## Mutation budget and exclusions

A future genuine APPLY may be eligible only for the reviewed controller's bounded activation behavior:

- apply-lock lifecycle: maximum 1;
- release materialization: maximum 1;
- atomic `current` pointer swap: maximum 1;
- release deletion: 0;
- automatic retry: 0;
- automatic cleanup: 0;
- automatic rollback: 0;
- DB writes: 0;
- credential/permission mutation: 0;
- package/systemd/service/Docker/network/Cloudflare mutation: 0.

The current Dashboard release controller remains the authority for descriptor-safe candidate verification, exact current/candidate revalidation, lock semantics, private partial-copy evidence, previous-release retention and post-mutation fail-closed behavior.

## Queue progression

For the current already-deployed `5f773934...` candidate:

```text
#28 = WAITING
reason = WAITING_P10_DASHBOARD_EXECUTOR_SOURCE_AND_NOOP_CLASSIFICATION
```

After this source capability is merged and exact-main CI is green, that historical candidate still must not be promoted merely to complete P10. The next genuine Dashboard source delta must separately provide:

1. reviewed/merged exact source SHA and exact-SHA CI;
2. source-derived root-owned candidate staging under the reviewed normal staging namespace;
3. trusted-controller read-only PLAN;
4. `observedCurrent != sourceSha`;
5. exact `candidateSha256`;
6. a queue contract matching the static operation;
7. a separately owner-authored LIVE-AUTH after all fresh baseline/provenance checks.

READY remains eligibility only. Merge never authorizes staging or production APPLY.
