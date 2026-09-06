# Hermes Deals origin broker request operator

Status: **source-only recovery hardening for RPi5_main #402**.

This document defines the capability-specific client side of the already reviewed Hermes origin broker socket. It does not authorize a broker request, replay consume, helper execution, audit invocation, trusted-checkout mutation, service change, deploy, or production-data mutation.

## Incident that exposed the missing operator

The post-recovery one-canary path used `ops-workflows#34` and owner-authored `deploy-authorizations#11`. At 2026-09-06 20:17:57 CEST the broker accepted one UNIX-socket connection and returned only:

```text
HERMES_ORIGIN_BROKER=REJECTED reason=invalid_identity_frame
```

Read-only reconciliation proved that this rejection occurred in `parse_broker_transport_request()` before runtime composition, canonical revalidation, durable replay consumption, helper launch, or audit evidence creation. The destination evidence directory for that canary remained absent.

The cause was client-side framing: the manual Python snippet serialized valid JSON but omitted the source-required final newline. The broker correctly requires exactly one UTF-8 JSON frame ending in one `\n` and rejects malformed frames before authority is entered.

`deploy-authorizations#11` is historical and must not be retried or reused.

## Canonical operator contract

`scripts/send-hermes-deals-origin-broker-request.py` removes socket framing from the human procedure.

The caller controls exactly one value: `authorization_issue_number`. Everything else is source-fixed:

- request schema `rozkalns.hermes-deals.origin-dispatch-request.v1`;
- socket `/run/rozkalns-hermes-deals-origin-broker/request.sock`;
- compact JSON serialization with exactly one trailing newline;
- request maximum 256 bytes;
- UNIX stream socket only;
- 65 second socket timeout;
- one connect/send attempt only;
- `shutdown(SHUT_WR)` after the single frame;
- response maximum 8192 bytes;
- expected receipt schema `rozkalns.hermes-deals.origin-broker-dispatch-receipt.v1`;
- receipt authorization issue number must match the request.

There is no CLI selector for schema, socket/path, timeout, source SHA, repository, operation, capability, command, shell, argv, environment, UID/GID, helper, evidence path or retry policy. The operator also requires effective UID 0 before opening the socket; obtaining that authority remains outside the source contract.

## Fail-closed one-shot semantics

Before a socket connection succeeds, a local operator failure reports `connection_started=false`. That fact alone does not grant retry authority; the current owner authorization and TTL must still be revalidated.

After `connect()` succeeds, any send, receive, timeout or receipt-validation error reports `connection_started=true retry_forbidden=true`. No automatic reconnect, fallback path, cleanup, replay reset, rollback or alternate execution exists in the operator.

A valid broker receipt is printed as the only stdout line. Business success or failure remains authoritative in that broker receipt. The operator does not reinterpret `FAIL_CLOSED` as retryable.

## Future LIVE use

Before any future invocation, automation must freshly prove all existing canary prerequisites and additionally bind:

1. exact merged `RPi5_main` SHA containing this operator;
2. exact operator Git blob/source identity;
3. trusted checkout clean and exact at that merged SHA;
4. one genuine current READY envelope;
5. one fresh human-owner-authored LIVE-AUTH with a new request ID and valid TTL;
6. broker socket/runtime poststate required by the existing #191 contract.

Only a separate explicit LIVE authorization may permit one root invocation of the operator. Merge of the source PR never grants that authority. The invocation carries only the freshly authorized LIVE-AUTH issue number and may occur once.

If the first broker connection starts, the LIVE authorization is treated as consumed for retry purposes regardless of the eventual broker result. Evidence collection after an error is read-only unless a new owner authorization explicitly grants a recovery mutation.
