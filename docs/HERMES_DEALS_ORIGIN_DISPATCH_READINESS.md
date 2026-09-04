# Hermes Deals origin audit — privileged dispatcher and broker source boundary

Status: **#361 MERGED / #363 BROKER INSTALLATION-WIRING SOURCE GATE / DISPATCH DISABLED / HOST WIRING DISABLED / NOT LIVE-INSTALL ELIGIBLE**

Tracking:

- current work item: `RPi5_main#363` / Draft PR #364
- completed privileged-dispatch plan: `RPi5_main#361` / PR #362
- completed pull-helper binding: `RPi5_main#359` / PR #360
- completed privileged-consumer gate: `RPi5_main#356` / PR #357
- completed identity-only request gate: `RPi5_main#354` / PR #355
- completed registry reconciliation: `RPi5_main#352` / PR #353
- runner-independent helper source: `hermes-deals#834` / PR #840
- Hermes runner migration: `rozkalnsandris/hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Current source baseline

At #363 creation:

- `RPi5_main/main = 8c157f0f6caf6258ebab7765a9b9ec2934070964`;
- exact-main Validate #814, FAST-LANE #270 and GITHUB-ONLY #258 are SUCCESS;
- `hermes-deals/main = 2f47f64ab15e767f4e53ad182326e64e313d5094`;
- Hermes Deals CI #1775 and GITHUB-ONLY #101 are SUCCESS;
- runner-independent helper blob is `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`.

These are source-review anchors only. They prove no current RPi5 files, ownership, permissions, credentials, units, sockets, runner state or runtime health.

## Completed dispatcher boundary

PR #362 merged the source-only `hermes_deals_origin_privileged_dispatcher.py` contract. The caller still supplies only:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

`prepare_hermes_deals_origin_privileged_dispatch()` calls the mandatory double canonical revalidation consumer and derives both helper arguments internally:

- `registered_source_sha` = the fully revalidated canonical Hermes source SHA;
- `as_of` = the UTC calendar date of the already validated GitHub owner authorization `created_at`.

The dispatcher source fixes:

- operation `hermes-deals.origin-path-audit.v1`;
- capability `origin-path-audit`;
- helper source blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- helper path `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- argument names exactly `registered_source_sha`, `as_of`.

It has no process-launch surface.

## #363 capability-specific broker source

#363 adds `hermes_deals_origin_privileged_broker.py`. Its UNIX-socket transport accepts exactly one bounded UTF-8 newline-framed JSON object, maximum 256 bytes, with only the existing identity-only request schema. Duplicate keys, extra fields, multiple frames, CR/NUL framing, oversized input and invalid UTF-8/JSON fail closed before canonical revalidation.

The broker does not accept a prebuilt dispatch plan. It calls `prepare_hermes_deals_origin_privileged_dispatch()` itself, then rechecks the exact operation, source repository, capability, helper source blob, installed helper path, two argument names and the canonical argument tuple. Any live flag entering the plan fails closed.

The broker envelope deliberately contains no callable, shell, executable selector, arbitrary path, argv extender, environment selector, UID/GID selector, unit selector or output path.

## Poller-to-broker trust boundary

The proposed source-only host transport is a dedicated systemd UNIX stream socket:

- socket unit: `rozkalns-hermes-deals-origin-broker.socket`;
- path: `/run/rozkalns-hermes-deals-origin-broker/request.sock`;
- owner: `root`;
- group: `rozkalns-deploy-executor`;
- mode: `0660`;
- `Accept=yes`;
- `MaxConnections=1`.

The per-connection service is `rozkalns-hermes-deals-origin-broker@.service` and is source-fixed to `/usr/local/libexec/rozkalns-hermes-deals-origin-broker`. It is root-owned by design because this is the future narrow privilege boundary, but the caller cannot select a service, executable, arguments, environment or capability.

The service contract includes `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, private devices/tmp, namespace/SUID/SGID/realtime hardening, bounded runtime and a capability bounding set limited to `CAP_SETUID CAP_SETGID` for the reviewed helper's fixed root-to-audit-user transition. It exposes no writable privileged path in this source gate.

The existing `rozkalns-deploy-executor.service` poller is not modified. It remains the unprivileged `rozkalns-deploy-executor` user/group with `NoNewPrivileges=true`, empty ambient capability set and no generic sudo/root/Docker-socket authority.

The generic `ops/bin/rozkalns-deploy-dispatch` remains `DISABLED` and is not repurposed as a root broker.

## Installation manifest

`ops/deploy/hermes-deals-origin-broker-installation.json` freezes the reviewed source contract for:

- broker module and broker entrypoint target paths, owner/group/modes;
- socket/service unit target paths and modes;
- socket path/group/mode;
- source credential path `/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem` with `root:root 0600` posture;
- reviewed Hermes helper source/blob/path/interface;
- root-owned registration path `/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json` mode `0600`;
- fixed probe path and registration-bound probe digest;
- root-owned evidence root `/var/lib/hermes-deals-audits/origin-path-audit/evidence` mode `0700`.

The manifest intentionally has `eligible_source_sha=null` with `POST_MERGE_EXACT_MAIN_BIND_REQUIRED`. It is not a host installer and is not LIVE authority.

## Blocking authenticated source-read prerequisite

The current source cannot safely compose a live broker yet. `p9_source_auth.py` is explicitly allowlisted only for `rozkalnsandris/rozkalns-control-center`; #363 does not silently widen that App/repository scope and does not create/change any credential, App installation or permission.

The broker service source names a future root-only credential path, but its entrypoint remains fail-closed and returns `SOURCE_AUTHORITY_UNPROVEN`. Therefore:

`SOURCE_READ_AUTHORITY_PROVEN=false`

`HELPER_PROCESS_LAUNCH_IMPLEMENTED=false`

`LIVE_INSTALL_ELIGIBLE=false`

A later source gate must prove the exact authenticated Hermes GitHub source/Actions read authority and implement/review the bounded fixed helper launch surface. That source work still must keep all live flags false.

## Required false flags

- production registry `execution_enabled=false`;
- generic dispatcher remains disabled;
- `privileged_dispatch_enabled=false`;
- `host_wiring_enabled=false`;
- `genuine_hermes_audit_authorized=false`;
- `runner_retirement_eligible=false`;
- `production_mutation_started=false`.

`HermesDealsOriginAuditAdapter.apply()` remains fail-closed.

## Gate sequence

1. **#352 complete** — dormant operation registration.
2. **#354/#355 complete** — identity-only request.
3. **#356/#357 complete** — double canonical revalidation consumer.
4. **Hermes #834/#840 complete** — runner-independent capability helper.
5. **#359/#360 complete** — helper provenance/interface and host-evidence binding.
6. **#361/#362 complete** — immutable capability-specific dispatcher plan, no launch.
7. **#363 current** — broker/socket/service/install-security source contract; source-read authority and process launch intentionally unresolved/fail-closed.
8. **Next source prerequisite** — prove exact Hermes authenticated source/Actions read authority and exact bounded helper launch source; keep live flags false.
9. **Source merge/exact-main bind** — bind eligible source SHA and fresh CI/security evidence.
10. **LIVE host installation/activation** — separate explicit owner authorization only after all source prerequisites are complete.
11. **STRICT genuine canary** — separate authorization for exactly one read-only origin audit.
12. **Runner retirement** — only after accepted replacement canary and separately authorized LIVE retirement.

A merge of #363 does not authorize any later gate.

## Current classification

`CURRENT_WORK_ITEM=RPi5_main#363`

`CURRENT_PHASE=4`

`GLOBAL_EXECUTION_ENABLED=false`

`PRIVILEGED_CONSUMER_IMPLEMENTED=true`

`RUNNER_INDEPENDENT_PULL_HELPER_SOURCE_BOUND=true`

`PRIVILEGED_DISPATCH_PLAN_IMPLEMENTED=true`

`BROKER_BOUNDARY_IMPLEMENTED=true`

`SOURCE_READ_AUTHORITY_PROVEN=false`

`HELPER_PROCESS_LAUNCH_IMPLEMENTED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`LIVE_INSTALL_ELIGIBLE=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`HERMES_AUDIT_RUNNER_RETIREMENT_ELIGIBLE=false`

`HERMES_RELEASE_RUNNER_IN_SCOPE=false`

`PRODUCTION_MUTATION_STARTED=false`
