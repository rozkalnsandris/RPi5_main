# Control Phase 5 production visibility GET-only producer

## Purpose

This source slice provides a bounded non-root producer for the existing
`ProductionVisibility` contract without granting that producer direct access to
root-owned controlled-deploy state.

The trust boundary is split in two:

1. the existing root-run `rpi5-dashboard-evidence` broker reads the already
   reviewed `/var/lib/rpi5-deploy` controlled-deploy state;
2. a dedicated broker helper publishes one sanitized, full-SHA Phase 5 snapshot
   below `/var/lib/dashboard-rpi5/evidence` for the non-root producer.

Repository source or GitHub state is never treated as proof of production state.

## Source mapping

- root broker helper: `ops/lib/phase5-production-visibility-evidence.py`
- existing broker wrapper: `ops/bin/rpi5-dashboard-evidence`
- non-root producer: `ops/lib/deploy_executor/control_phase5_production_visibility_producer.py`
- producer CLI: `ops/bin/rpi5-control-phase5-production-visibility`
- focused tests: `tests/test-control-phase5-production-visibility-producer.py`

The existing `ops/lib/dashboard-evidence.py` deployment evidence contract and
`deployments.json` remain unchanged. The existing systemd service and timer
source also remain unchanged.

## Root broker authority

Only the root broker helper may read `/var/lib/rpi5-deploy`. It reads exactly:

1. `/var/lib/rpi5-deploy/latest-success`;
2. the selected `/var/lib/rpi5-deploy/transactions/<transaction-id>` directory;
3. that directory's `transaction.json`.

The controlled-deploy transaction must use schema
`rpi5.controlled-deploy-transaction.v1`, identify repository
`rozkalnsandris/RPi5_main`, have status `success`, contain a full lowercase
40-character commit whose prefix matches the transaction id, and contain a UTC
completion timestamp. Directories/files must be real objects rather than
symlinks, root-owned in production, and not group/world writable. Reads are
bounded and use `O_NOFOLLOW`.

Before attempting the raw-state read, every broker run atomically publishes an
`UNAVAILABLE` snapshot. A successful validated observation replaces it with an
`AVAILABLE` snapshot. This prevents a fresh previously valid observation from
remaining authoritative when the current raw observation fails.

## Sanitized Phase 5 snapshot

The only non-root observation authority is:

`/var/lib/dashboard-rpi5/evidence/phase5-production-visibility.json`

The exact schema is `rpi5.phase5-production-visibility-evidence.v1` with fields:

- `schema`;
- `status` (`AVAILABLE` or `UNAVAILABLE`);
- `repository`;
- `transactionId`;
- `productionSha`;
- `completedAt`;
- `observedAt`.

For `AVAILABLE`, `transactionId`, `productionSha`, and `completedAt` are
concrete validated values and `productionSha` is always the full 40-character
SHA. For `UNAVAILABLE`, those three fields are `null`. The snapshot is bounded,
atomically replaced, mode `0644`, root-owned in production, and contains no
secret/config/runtime-environment data.

The existing broker wrapper requires both helper files to be root-owned and not
group/world writable before invoking them. No ACL, supplementary group,
capability, permission, service, or timer expansion is part of this source fix.

## Non-root producer authority

`rpi5-control-phase5-production-visibility` reads only the sanitized snapshot;
it no longer reads `/var/lib/rpi5-deploy` directly. The producer validates:

- real root-owned broker evidence directory/file metadata in production;
- exact field set and schema;
- repository identity;
- `AVAILABLE` status;
- transaction id format;
- full 40-character SHA and transaction-prefix agreement;
- canonical UTC `completedAt` and `observedAt` timestamps;
- `completedAt <= observedAt`.

The broker's actual `observedAt` is passed into the existing
`normalize_production_visibility` boundary. That existing contract fails closed
when evidence is from the future or older than 300 seconds. The producer does
not replace broker observation time with its own current time.

If `productionSha == mainSha`, `deployImpact` is `NO_DEPLOY`. If the SHAs differ,
`deployImpact` remains `UNKNOWN` with deterministic blocker codes. Runtime,
health, and rollback remain `UNKNOWN`; this source does not infer them from
systemd, Docker, endpoints, databases, logs, configuration, or repository state.

## Failure behavior

Missing, unsafe, malformed, unavailable, stale, contradictory, wrong-repository,
wrong-schema, or wrong-commit broker evidence fails closed with public-safe STOP
codes. The producer performs no retry, repair, fallback observation, permission
change, or alternate target selection.

The producer CLI STOP receipt continues to state:

- `authorization_consumed=false`;
- `mutation_started=false`;
- `credential_access=NO`;
- `network_request=NO`.

## Source readiness versus production state

This change is source-only. Merge does not install the new broker helper, replace
the installed broker wrapper, run the broker, change systemd, or make the new
snapshot exist in production.

A later production sequence must separately authorize and prove the exact
runtime rollout of the reviewed broker helper/wrapper before the GET-only
producer is retried. After that rollout, preflight must refresh the exact current
`RPi5_main/main` SHA and required CI, verify exact checkout/source provenance,
verify a fresh broker snapshot, and only then invoke:

```text
python3 /path/to/exact-reviewed-checkout/ops/bin/rpi5-control-phase5-production-visibility --expected-main-sha <MAIN_SHA>
```

The producer itself neither requires nor elevates privilege. It must run under an
identity that can read the sanitized `0644` broker snapshot. No direct permission
to `/var/lib/rpi5-deploy` is required or authorized.

## Explicit non-authorities

This source does not authorize or perform:

- secrets, private keys, credentials, process/container environments;
- application configuration, databases, backups, request/application logs;
- ACL/group/permission changes or capabilities;
- service/timer installation, restart, reload, enablement, or activation;
- Docker, networking, Cloudflare, D1, Queue, DNS, routes, or bindings;
- signer activation, network delivery, deploy, rollback, or other production mutation.
