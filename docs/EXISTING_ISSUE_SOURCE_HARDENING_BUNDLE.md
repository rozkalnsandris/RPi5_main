# Existing-issue source hardening bundle — #464

Status: **SOURCE ONLY / LIVE DISABLED**

Issue #464 packages ten existing security, reliability and audit-tooling jobs into
one reviewable source outcome. It does not close the parent issues when they still
require runtime evidence or a later owner-authorized mutation.

## Job reconciliation

| Job | Parent | Source result | Evidence / remaining gate |
| --- | --- | --- | --- |
| 1 | #453 | DONE | `ops/contracts/existing-issue-source-hardening-v1.json` now freezes the exact host/cross-repo gaps, canonical owner class, required evidence class and future gate. |
| 2 | #27 | DONE | Existing bounded AdGuard collector/verifier/tests already implement the privacy-safe source tooling; four live samples remain a later read-only evidence requirement. |
| 3 | #93 | DONE | The shared-UID publisher threat boundary, dedicated identity target, raw-credential isolation and retirement sequence are frozen in the machine contract. |
| 4 | #110 | SOURCE_READY_LIVE_LATER | `ops/lib/hermes_publisher_guard.py` validates immutable repository/branch/base/parent/subject/path/remote-main evidence with no Git/SSH/shell execution. Exact Hermes generated-path binding, credential placement, installation and real publication remain future gates. |
| 5 | #117 | DONE | Existing restore-drill operator, adversarial tests and docs already enforce isolated restore roots, defensive archive validation, exact verifier provenance, sanitized evidence and cleanup/failure propagation. Real retained backups are not touched here. |
| 6 | #177 | DONE | Existing public-safe hostname/security registry remains canonical; #464 regression locks the no-secret/no-live ownership model. |
| 7 | #179 | SOURCE_READY_LIVE_LATER | Existing GET-only reconciliation operator/offline tests remain source-ready. This bundle does not run it against the real Cloudflare account. |
| 8 | #206 | SOURCE_READY_LIVE_LATER | Public-safe exact-scope WAF/rate-limit proposal classes, rationale and inverse-removal rollback are modeled without Cloudflare writes. |
| 9 | #207 | SOURCE_READY_LIVE_LATER | Machine endpoint classes now bind provider HMAC, Service Auth/application auth, replay/dedupe, method/content/body/timeout and privacy-safe observability requirements. |
| 10 | #189 | SOURCE_READY_LIVE_LATER | Secret-free staged consumer migration, per-consumer rollback and final legacy-revocation gate are frozen; no credential, MQTT or service mutation is authorized. |

## Hermes publisher boundary

The guard is deliberately inert. It accepts a source-owned immutable
`PublicationSpec` and observed Git metadata, then either fails closed or returns
`SOURCE_VALIDATED_NO_PUSH`; it performs no subprocess, network push, SSH, credential
read or shell execution.

The source guard requires:

- exact `rozkalnsandris/hermes-tech` repository and `main` branch;
- exact 40-character base/publication/parent/remote-main SHAs;
- direct parent equals the frozen base;
- remote `main` remains the frozen base at the final race guard;
- exact publication subject;
- observed changed paths equal the frozen expected path set;
- only relative non-traversing paths;
- fast-forward-only intent and a later exact post-push SHA check.

Production wiring is intentionally absent. The exact generated-content path set must
be bound by the later Hermes Tech producer/consumer integration review; this bundle
does not guess it or create generic caller-selected path authority.

## Cloudflare compensating controls

The machine contract removes Bot Fight Mode as a dependency and preserves always-on
DDoS, Managed WAF and Access/application authentication. Proposed controls are
narrow hostname/trust-class/path-class/method shapes only. Dynamic cloud-runner IPs
and User-Agent matching are explicitly forbidden as primary identity.

Every proposed rule has a rationale and an exact inverse-removal rollback concept.
No rule is applied by this source outcome.

## M2M and webhook model

The source model distinguishes provider webhooks, service-authenticated APIs and
read-only health endpoints. Provider webhooks require HMAC-SHA256 over original
request bytes plus stable delivery identity dedupe. Mutating service APIs require
Service Auth/application authorization as applicable and an idempotency/replay
identity. All classes require bounded methods, body handling, timeout and sanitized
logging. Rate limiting is defense in depth, never authentication.

## MQTT legacy credential migration

Migration is staged per consumer:

1. sanitized consumer identity inventory;
2. least-privilege replacement identity design;
3. exact preflight;
4. separately owner-authorized per-consumer migration;
5. postcondition proof and rollback readiness;
6. only after all required consumers pass, a separate final legacy-revocation gate.

Credential values remain outside Git and argv. This source bundle does not read
broker password files, publish MQTT messages, restart services or revoke credentials.

## Safety boundary

`runtime_live_authority=false` and `production_mutation_started=false`.

No sudo/root, Docker/systemd mutation, Cloudflare write, DNS/network/firewall write,
credential read/rotation, MQTT publish, retained-backup decrypt/restore, service
restart, deploy, destructive cleanup or reboot is part of #464.
