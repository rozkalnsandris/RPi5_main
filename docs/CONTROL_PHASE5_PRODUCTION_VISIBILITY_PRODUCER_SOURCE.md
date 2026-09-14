# Control Phase 5 production visibility GET-only producer

## Purpose

This source slice provides a bounded protected-host producer for the existing
`ProductionVisibility` contract. It closes the source gap for authoritative
`RPi5_main` production SHA observation without granting broad runtime, secret,
network, database, Docker, systemd, or credential authority.

The producer is intentionally conservative. It observes only the already
reviewed controlled-deploy state below `/var/lib/rpi5-deploy` and passes its
result through `control_phase5_production_visibility.normalize_production_visibility`.
It never treats repository source as proof of production state.

## Source mapping

- library: `ops/lib/deploy_executor/control_phase5_production_visibility_producer.py`
- CLI source: `ops/bin/rpi5-control-phase5-production-visibility`
- tests: `tests/test-control-phase5-production-visibility-producer.py`

The CLI source is invoked through `python3` from an exact reviewed checkout; no
installed executable is created by this slice. A repository merge does not
install, activate, or execute it on the host.

## Exact observation authority

The only production observation root is `/var/lib/rpi5-deploy`.

The producer reads exactly this chain:

1. `/var/lib/rpi5-deploy/latest-success`;
2. the selected `/var/lib/rpi5-deploy/transactions/<transaction-id>` directory;
3. that directory's `transaction.json`.

The transaction id must match the reviewed controlled-deploy id format. The
transaction must use schema `rpi5.controlled-deploy-transaction.v1`, identify
repository `rozkalnsandris/RPi5_main`, have status `success`, contain a full
lowercase 40-character commit whose prefix matches the transaction id, and
contain a UTC completion timestamp.

Production directories/files must be real objects rather than symlinks. The
producer uses bounded `O_RDONLY|O_NOFOLLOW` reads; production metadata must be
root-owned and not group/world writable. Pointer and transaction byte sizes are
bounded. Duplicate JSON keys fail closed.

No other host path is an observation authority for this slice.

## Output semantics

Success is exactly the existing ten-field `ProductionVisibility` object:

- `projectId = rpi5-main`;
- `repository = rozkalnsandris/RPi5_main`;
- `mainSha` is the explicit expected fresh GitHub main SHA supplied by the caller;
- `productionSha` is the full controlled-deploy commit;
- `observedAt` is the current UTC read time and is validated by the existing
  sanitizer in the same call.

If `productionSha == mainSha`, `deployImpact` is `NO_DEPLOY`. If the SHAs differ,
this source does **not** guess rollout semantics: `deployImpact` is `UNKNOWN`
and blocker codes include `PRODUCTION_SHA_DIFFERS_FROM_MAIN` and
`DEPLOY_IMPACT_OBSERVATION_UNAVAILABLE`.

No reviewed Phase 5 source currently authorizes this producer to infer runtime,
health, or rollback state from endpoint dashboards, source files, systemd,
Docker, databases, logs, or configuration. Those fields therefore remain
`UNKNOWN` with deterministic blockers:

- `RUNTIME_OBSERVATION_UNAVAILABLE`;
- `HEALTH_OBSERVATION_UNAVAILABLE`;
- `ROLLBACK_OBSERVATION_UNAVAILABLE`.

This is fail-closed evidence, not a fabricated PASS. A downstream gate that
requires concrete runtime/health/rollback evidence must remain blocked until a
separately reviewed observation authority exists.

## Failure behavior

Unsafe, missing, malformed, contradictory, wrong-repository, wrong-schema, or
wrong-commit controlled-deploy state emits only a public-safe STOP code. The CLI
also fails closed for a non-root production execution identity.

STOP receipts state:

- `authorization_consumed=false`;
- `mutation_started=false`;
- `credential_access=NO`;
- `network_request=NO`.

No retry, repair, cleanup, write, fallback source, or alternate target is
performed by the producer.

## GET-only preflight sequence

A future production preflight must first refresh GitHub and bind the invocation
to the exact current `RPi5_main/main` SHA with required checks passing. With
that SHA `<MAIN_SHA>`, the reviewed GET-only invocation is:

```text
sudo python3 /path/to/exact-reviewed-checkout/ops/bin/rpi5-control-phase5-production-visibility --expected-main-sha <MAIN_SHA>
```

The checkout/source provenance for that future invocation must itself be
revalidated before execution. This document does not authorize executing the
command in production, creating a checkout, changing `/var/lib/rpi5-deploy`, or
performing any later signer/network delivery.

The successful JSON can be supplied as the `visibility` member of the existing
Phase 5 observation delivery envelope. Because runtime/health/rollback remain
UNKNOWN in this source slice, success here alone is not a production verification
PASS and does not authorize signer activation, credential access, delivery,
merge, deploy, or LIVE mutation.

## Explicit non-authorities

This source does not read or expose:

- secrets, private keys, credential contents, process/container environments;
- application configuration, databases, backups, request/application logs;
- Docker or systemd runtime state;
- Cloudflare, Worker, D1, Queue, DNS, routes, bindings, or network endpoints.

It performs no filesystem write, service change, network request, cleanup,
rollback, deploy, or other production mutation.
