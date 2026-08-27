# Owner-authorized pull deploy executor v1

Status: P0 SOURCE CONTRACT
Roadmap: `RPi5_main#236`
Canonical program: `docs/AUTOMATION_MASTER_PLAN.md`
Shared queue policy: `rozkalnsandris/ops-workflows/docs/GITHUB_ONLY_LIVE_ALL.md`

## 1. Purpose and authority

Define the security contract for a pull-based RPi5 deployment executor that can consume a separately explicit owner decision from GitHub without SSH, a self-hosted GitHub Actions production runner, an inbound RPi5 webhook/API, or arbitrary remote shell execution.

This document is source-only. It authorizes no GitHub App creation/permission change, credential placement, host installation, root/sudo/systemd change, production deploy, DB write, Cloudflare change, or other live mutation. Repository-local deployment contracts remain stricter where applicable. Merge never authorizes deployment.

This is a cross-cutting transport/security track; it does not replace the ordered phases in `AUTOMATION_MASTER_PLAN.md`. P7+ live work remains blocked until the master plan separately names the exact live step as eligible.

## 2. Intended flow

```text
owner decision
  -> DEPLOY-QUEUE READY state in ops-workflows
  -> separate owner-authored LIVE-AUTH issue in ops-workflows
  -> outbound-only authenticated RPi5 polling
  -> auth/queue/source/CI/baseline revalidation
  -> source-controlled static operation registry
  -> fixed project adapter
  -> existing narrow project controller/root helper
  -> health + durable evidence
```

No GitHub-controlled value may become a shell command, executable path, arbitrary argv list, environment injection, Docker/systemctl/sudo passthrough, or dynamic import target.

## 3. Trust boundaries

### Owner

The configured owner authority is GitHub numeric user ID `277435981`; login text is display-only. A valid owner actor must also be returned by GitHub as `type=User`.

Compromise of the owner's GitHub account is equivalent to compromise of the owner authorization boundary and cannot be distinguished by this protocol.

### ChatGPT/GitHub operator path

ChatGPT may create LIVE-AUTH only after a separately explicit owner deployment/live instruction that satisfies the repository-local authorization contract. `START`, `turpini`, merge approval, GITHUB-ONLY, queue READY, historical chat state or a prior authorization must never imply LIVE-AUTH.

P9 must prove that the actual connected GitHub write path creates the authorization object with GitHub server metadata identifying the configured owner numeric ID. If the write appears as an App/Bot actor, execution fails closed until the transport is redesigned.

### Authorization store

`ops-workflows` stores only public-safe queue/authorization data. A READY queue item means eligible for consideration; it is never authority to execute.

### Critical credential invariant

**No autonomous RPi5 credential may have write authority over the GitHub surface from which owner authorization is accepted.**

The first executor authorization App, if later approved, therefore defaults to:

- repository scope: `rozkalnsandris/ops-workflows` only;
- Issues: **read-only**;
- Metadata: minimum/implicit read;
- all GitHub write permissions: no access;
- webhook: disabled.

The earlier proposal to give the same executor App `Issues: read/write` is rejected. Current GitHub documentation confirms that `Issues: write` permits issue/comment update operations; a validator credential that can rewrite accepted authorization material is not an independent authority validator.

Automatic GitHub result reporting, if added later, must use a separately reviewed reporting surface/capability that cannot create, edit, delete, relabel, close, reopen or otherwise forge accepted LIVE-AUTH authority. Until that is proven, local durable evidence plus an already-approved notification channel is safer than granting the executor GitHub write authority.

### Existing `Rozkalns Automation`

Remain unchanged:

- Actions: read;
- Contents: read;
- existing approved repository scope only.

It remains the source/CI truth reader for repositories in its contract. This track must not opportunistically add Issues/workflow/deployment/admin write permissions or repository scope.

### Unprivileged poller

The always-on poller runs without root, has no generic sudo path, should retain `NoNewPrivileges=true`, performs outbound HTTPS plus narrow local IPC/state operations, and never translates `operation_id` into a shell string.

### Privileged dispatcher

The privileged boundary accepts only a narrow request identity, then independently re-fetches/revalidates authorization and the source-controlled operation registry before entering a mutation-capable adapter. It does not trust SHA, command, path, argv, rollback command or mutation budget supplied by the unprivileged process.

## 4. LIVE-AUTH v1 transport

One normal GitHub Issue in `rozkalnsandris/ops-workflows`:

```text
[LIVE-AUTH][PENDING] <public-safe target alias>
```

It must be an Issue, not a pull request.

### Fixed TTL

Protocol v1 TTL is exactly **600 seconds (10 minutes)** from GitHub server `created_at`. It is not caller-selectable and is not extended by edits, comments, labels, reactions, retries, polling delays or restarts.

Age should be evaluated against the authenticated GitHub response `Date` header. Missing/malformed server time, material clock inconsistency or age above 600 seconds fails closed.

### Payload block

The body contains exactly one marked JSON authority block. Four backticks below are documentation delimiters only:

````text
<!-- rozkalns-live-auth:v1 -->
```json
{
  "schema": "rozkalns.live-auth.v1",
  "request_id": "UUIDv4",
  "queue_repository": "rozkalnsandris/ops-workflows",
  "queue_issue": 123,
  "source_repository": "rozkalnsandris/example",
  "source_sha": "0123456789abcdef0123456789abcdef01234567",
  "target_alias": "public-safe-target",
  "operation_id": "project.operation.v1",
  "expected_baseline": {
    "kind": "exact-or-resolver",
    "value": "public-safe bounded value"
  },
  "mutation_budget": [
    {"category": "reviewed-category-id", "max_operations": 1}
  ],
  "rollback_policy": "NONE",
  "exclusions": ["explicit exclusion"],
  "dependencies": []
}
```
<!-- /rozkalns-live-auth:v1 -->
````

Reject missing/multiple authority blocks, duplicate JSON keys, non-object roots, unknown top-level fields, type mismatches, oversized values, invalid Unicode or additional authority blocks.

`operation_id`, mutation categories, baseline resolver IDs and rollback policies are enums owned by source-controlled RPi5 policy. GitHub can select only already-reviewed values; it cannot define executable behavior.

### Canonical digest

After strict parsing, calculate a semantic SHA-256 over UTF-8 JSON serialized with lexicographically sorted keys, `,`/`:` separators without insignificant whitespace, normal JSON string encoding, and duplicate keys already rejected. This is conceptually equivalent to:

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

Also store SHA-256 of the exact raw issue body. Immediately before privileged dispatch, re-fetch and require both digests unchanged.

## 5. Acceptance algorithm

All checks are mandatory and ordered:

1. repository is exactly `rozkalnsandris/ops-workflows`;
2. resource is an open Issue, not a PR;
3. title matches LIVE-AUTH v1;
4. GitHub `user.id == 277435981` and `user.type == User`;
5. GitHub server time proves request age is within 600 seconds;
6. strict payload parsing succeeds;
7. GitHub issue ID and `request_id` are unseen in durable local state;
8. referenced queue issue is still open and exactly READY;
9. queue repo/SHA/target/operation/mutation envelope matches LIVE-AUTH;
10. exact source SHA exists and repository-local reachability/current-main rules pass;
11. required exact-SHA CI/review evidence is fresh and successful;
12. expected target baseline still matches or the reviewed resolver proves it;
13. static registry permits the operation/deploy class/mutation budget/rollback policy;
14. exact adapter/helper identities and cross-repository interface contracts are proven;
15. no new secret, permission, DB, infrastructure or undeclared mutation is required;
16. immediately before privileged dispatch, repeat authorization, queue, source/CI and baseline reads and require both accepted digests unchanged.

Unknown, incomplete, stale or ambiguous evidence is rejection, not permission.

## 6. Replay and crash safety

Use a durable trusted local state store; SQLite is the preferred first implementation unless P1 proves an equivalent simpler design.

Uniqueness must cover GitHub repository+issue identity and `request_id`.

Minimum states:

```text
DISCOVERED
VALIDATING
ACCEPTED
CONSUMED
VERIFYING
SUCCEEDED
REJECTED
EXPIRED
STOP_ERROR
```

Persist `CONSUMED` atomically **before** crossing into the mutation-capable adapter/IPC boundary. Entry into that boundary consumes authorization even if the adapter later finds that its first intended write cannot start. False-positive consumption is safer than accidental replay.

A crash after `CONSUMED` never auto-replays. Recovery requires preserved evidence and a new owner authorization unless a stricter repository-local contract explicitly defines another safe path.

## 7. Polling/API contract

No inbound RPi5 webhook is required. Polling must use:

- authenticated REST requests;
- fixed interval, initially about 2 minutes;
- serialized, not concurrent, requests;
- stable/specific query URLs;
- `ETag` + `If-None-Match` where supported;
- `Retry-After` and `X-RateLimit-*` handling;
- no busy retry on rate limiting;
- bounded pre-mutation transport retry only;
- no write/execution retry after mutation-capable execution starts.

GitHub documents that correctly authorized conditional GET requests returning `304 Not Modified` do not consume the primary REST rate limit.

Pin one currently supported REST API version in implementation and re-check official docs immediately before P2/P7 rather than relying on a historical header value.

GitHub App installation tokens must be minted on demand and never logged/persisted. Current GitHub documentation states they expire after one hour and can be further scoped down to selected repositories/permissions within the App installation grant.

## 8. Static operation registry

The source-controlled RPi5 registry is the only mapping from GitHub data to executable behavior. Each operation record must define:

- operation/schema version;
- source repository;
- target alias/class;
- allowed deploy classification;
- fixed adapter identity;
- required source/CI evidence;
- mutation categories and maximum counts;
- rollback policy enum;
- postconditions;
- LIVE-ALL eligibility class;
- cross-repository contract/version IDs.

Forbidden: shell snippets, GitHub-provided argv, user-controlled executable paths, environment injection, dynamic imports, generic sudo/Docker/systemctl passthrough. Unknown operations reject.

## 9. Rollback semantics

After mutation begins, error/ambiguity means evidence + STOP; no retry, cleanup, alternate path or rollback unless that exact behavior was pre-authorized.

A helper with built-in rollback is eligible only when the same reviewed rollback policy ID is present in:

1. the static registry;
2. the deploy queue envelope;
3. LIVE-AUTH;

and the helper identity, rollback scope and operation counts are revalidated. `rollback_policy=NONE` forbids automatic rollback. A helper that cannot enforce this distinction is not executor-eligible.

## 10. Threat matrix

| Threat | Mandatory defense |
| --- | --- |
| Executor forges owner approval | Executor credential read-only on authorization surface; exact numeric owner actor |
| App edits owner issue/comment | No executor Issues write on authorization repo |
| Stale authorization | Fixed 600-second server-time TTL |
| Edited authorization | Raw-body + canonical-payload digests re-fetched before dispatch |
| Replay after success/failure/crash | Durable unique IDs; atomic `CONSUMED` before privileged boundary |
| Queue drift | Fresh READY/envelope revalidation |
| Source drift | Exact immutable SHA + repository-local reachability/current-main rules |
| CI drift | Fresh exact-SHA Actions/check semantics |
| Baseline drift | Immediate pre-mutation baseline revalidation |
| Malicious operation ID | Static allowlisted registry |
| Shell/path injection | No command/path/argv authority from GitHub |
| Poller compromise | No generic sudo; privileged dispatcher independently revalidates |
| Confused deputy | Dispatcher accepts only request identity and re-reads authority itself |
| GitHub outage/partial response | Fail closed before mutation |
| Rate limiting | Conditional GET, serialized calls, retry headers, hard ceiling |
| Local state loss/corruption | Disable mutation path until integrity is restored |
| Helper/interface drift | Exact identity + cross-repo contract verification |
| Helper failure after mutation | Evidence + STOP; only explicitly authorized built-in rollback |
| Receipt/reporting failure | Never repeat deployment merely to repair reporting |
| Public evidence leakage | Public-safe bounded schema; reject protected data |

## 11. Result reporting separation

P0 deliberately grants no autonomous GitHub write credential. Local evidence must retain request ID, source SHA, target, operation, consumption state, mutation counts, health/postconditions and a sanitized failure class.

A later automatic GitHub receipt channel is allowed only after proving it cannot mutate the authorization surface. Reporting failure must never cause deployment replay.

## 12. Canary rules

- No dummy commit, placeholder deployment or invented production delta just to test automation.
- P9 uses a genuine prepared owner decision in mutation-disabled/dry-run mode.
- P10 uses the lowest-risk genuine READY ordinary deployment available then.
- High-risk control-plane operations such as Hermes Tech pull-deploy activation remain later STRICT work.

## 13. External documentation reviewed for P0

Reviewed 2026-08-27 against current official GitHub documentation:

- REST best practices: authenticated/serialized polling, conditional requests, `Retry-After`, bounded rate-limit handling;
- GitHub App installation authentication: short-lived installation tokens and repository/permission scoping;
- Issues/Issue Comments permissions: `Issues: write` authorizes update operations, motivating the read-only authorization-reader boundary.

Re-check these semantics immediately before P2/P7 because API versions and product behavior can change.

## 14. P0 exit gate

P0 is complete only when:

- this threat model and `AUTOMATION_MASTER_PLAN.md` reconciliation are reviewed in a focused PR;
- issue #236 is reconciled with the read-only authorization-reader invariant;
- no GitHub App permission, credential, host/runtime, production, DB or Cloudflare mutation occurred.

After P0 reaches Ready, STOP for explicit merge. P1 is not implicitly authorized by P0.