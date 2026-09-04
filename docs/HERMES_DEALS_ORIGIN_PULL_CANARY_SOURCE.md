# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE-REGISTERED / PULL-HELPER BOUND / DISPATCH PLAN MERGED / BROKER SECURITY GATE / GLOBALLY EXECUTION-DISABLED / STRICT / NOT HOST-EXECUTABLE**

Tracking:

- current broker installation/wiring source gate: `RPi5_main#363` / Draft PR #364
- completed dispatcher source gate: `RPi5_main#361` / PR #362
- completed helper-binding gate: `RPi5_main#359` / PR #360
- completed privileged-consumer gate: `RPi5_main#356` / PR #357
- completed identity-only request gate: `RPi5_main#354` / PR #355
- completed registry reconciliation: `RPi5_main#352` / PR #353
- runner-independent helper source: `hermes-deals#834` / PR #840
- Hermes Deals migration: `rozkalnsandris/hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Current routing

Phase 4 remains the residual Hermes Deals origin-audit migration. The production operation registry contains `hermes-deals.origin-path-audit.v1` but remains globally `execution_enabled=false`.

The operation remains:

- authorization class `STRICT`;
- ordinary LIVE-ALL eligibility `false`;
- rollback policy `NONE`;
- invocation budget exactly one future `hermes-deals.read-only-audit-invocation`;
- adapter `apply()` fail-closed.

PR #362 merged the capability-specific source dispatch plan, but no helper process launch exists and no production selector/cutover occurred.

## Reviewed cross-repository source anchors

At #363 creation:

- `RPi5_main/main = 8c157f0f6caf6258ebab7765a9b9ec2934070964`;
- exact-main Validate #814, FAST-LANE #270 and GITHUB-ONLY #258 are SUCCESS;
- `hermes-deals/main = 2f47f64ab15e767f4e53ad182326e64e313d5094`;
- Hermes Deals CI #1775 and GITHUB-ONLY #101 are SUCCESS;
- runner-independent pull-helper blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

The helper fixes capability `origin-path-audit`, root-owned registration schema/path, machine identity `rpi5`, installed path `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`, fixed probe identity and evidence root. Its caller-visible arguments remain exactly `registered_source_sha` and `as_of`.

These are source anchors only; they prove no live RPi5 installation or runtime state.

## Identity-only request and canonical derivation

The privileged request remains exactly:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

Caller-supplied source SHA, `as_of`, command, shell, capability, executable/path, argv, environment, UID/GID, systemd unit, URL, output or evidence path is forbidden.

The mandatory consumer revalidates the complete canonical state twice, with sanitized host evidence between those reads. `registered_source_sha` comes only from the fully revalidated source evidence; `as_of` is the UTC calendar date derived from the validated GitHub owner authorization `created_at`. Both values are non-caller authority.

## Completed dispatch-plan boundary

`hermes_deals_origin_privileged_dispatcher.py` calls the double-revalidation consumer and source-binds:

- operation `hermes-deals.origin-path-audit.v1`;
- capability `origin-path-audit`;
- helper blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- installed helper path `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- argument names `registered_source_sha`, `as_of`;
- argument values only from canonical evidence.

It emits source data only and contains no subprocess/shell/sudo launch surface.

## #363 broker and socket source contract

The new source-only broker adds a second fail-closed boundary before any future process launch can exist:

1. one UNIX socket frame only;
2. maximum 256 bytes;
3. UTF-8 JSON with exactly the existing request schema/issue identity;
4. duplicate keys, extra fields, CR/NUL framing, multiple frames and oversized payloads rejected;
5. broker calls the reviewed dispatcher preparation path itself;
6. caller cannot submit a prebuilt plan;
7. exact operation/repository/capability/helper/blob/path/argument shape is rechecked;
8. any live flag present in the plan fails closed.

The proposed source transport is:

- `rozkalns-hermes-deals-origin-broker.socket`;
- `/run/rozkalns-hermes-deals-origin-broker/request.sock`;
- root-owned socket, group `rozkalns-deploy-executor`, mode `0660`;
- `Accept=yes`, `MaxConnections=1`;
- per-connection `rozkalns-hermes-deals-origin-broker@.service`;
- fixed broker install path `/usr/local/libexec/rozkalns-hermes-deals-origin-broker`.

The existing poller unit is unchanged and retains `NoNewPrivileges=true`. It is not granted sudo, root, Docker-socket, arbitrary unit or capability authority.

The generic `rozkalns-deploy-dispatch` remains disabled.

## Installation manifest is evidence, not an installer

`ops/deploy/hermes-deals-origin-broker-installation.json` records the exact intended path/owner/group/mode contract for the broker module, entrypoint, socket/service units, credential path, reviewed helper, registration, probe and evidence root.

It deliberately records:

- `eligible_source_sha = null`;
- `eligible_source_sha_status = POST_MERGE_EXACT_MAIN_BIND_REQUIRED`;
- `live_install_eligible = false`;
- source credential/permission mutation authorized = false.

No host path is created or changed by this source gate.

## Source-read authority is the current blocker

The existing `p9_source_auth.py` source App allowlist is control-center-only. #363 does not widen it and does not assume the host credential already has Hermes authority.

The future broker credential path is source-fixed as `/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem`, `root:root 0600`, but no key is created or copied and no App installation/permission change is authorized.

The inert broker entrypoint parses the identity frame and then returns `SOURCE_AUTHORITY_UNPROVEN`. Therefore the source deliberately remains:

- `source_read_authority_proven=false`;
- `helper_process_launch_implemented=false`;
- `privileged_dispatch_enabled=false`;
- `host_wiring_enabled=false`;
- `live_install_eligible=false`;
- `genuine_hermes_audit_authorized=false`;
- `runner_retirement_eligible=false`;
- `production_mutation_started=false`.

## Static selector and legacy runner stay unchanged

The production registry still points to the legacy `tools/runner/origin-path-rpi5-audit-dispatcher.sh` while global execution remains disabled. #363 does not replace that selector.

The existing `origin-path-rpi5-audit` workflow and `hermes-deals-audit` self-hosted runner therefore remain the residual path until a replacement is separately source-complete, installed, activated and proven. The separate `hermes-deals-release` runner remains outside this lane.

## Regression contract

Focused tests must prove:

1. request/socket framing is exact, bounded and identity-only;
2. extra authority and duplicate/multi-frame input is rejected before canonical revalidation;
3. broker invokes the existing dispatcher preparation path rather than accepting a caller plan;
4. exact helper provenance/path/two-argument contract remains bound;
5. broker and inert entrypoint contain no process-launch/shell/sudo/systemctl surface;
6. installation manifest has no eligible merged SHA and no LIVE eligibility;
7. socket is root-owned, narrow-group `0660` and serialized;
8. service is source-fixed and hardened with no writable privileged path in this gate;
9. existing poller `NoNewPrivileges=true` posture is unchanged;
10. generic deploy dispatcher remains disabled;
11. source App scope is not widened;
12. every dispatch/wiring/live/canary/retirement/production flag remains false.

## Next gates

#363 must first reach source Ready and STOP for separate MERGE authorization.

Even after a separately authorized #363 merge and fresh exact-main CI, **LIVE is still not next**. A new source prerequisite must prove exact authenticated Hermes GitHub source/Actions read authority and then implement/review the exact bounded helper launch surface while all live flags remain false.

Only after that source prerequisite is merged and exact-main-bound may a separate explicit LIVE authorization install/activate the reviewed host components. A still-separate STRICT authorization is required for exactly one genuine read-only audit canary. Runner retirement remains later and separately LIVE-authorized.
