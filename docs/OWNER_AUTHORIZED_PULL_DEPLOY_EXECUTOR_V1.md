# Owner-authorized pull deploy executor v1

Status: P0 SOURCE CONTRACT
Roadmap: `RPi5_main#236`
Canonical program: `docs/AUTOMATION_MASTER_PLAN.md`
Shared queue policy: `rozkalnsandris/ops-workflows/docs/GITHUB_ONLY_LIVE_ALL.md`

## 1. Purpose

Define the security and authorization contract for a pull-based RPi5 deployment executor that can consume an explicit owner decision from GitHub without exposing SSH, adding a self-hosted GitHub Actions production runner, accepting inbound webhooks on the RPi5, or accepting arbitrary remote shell commands.

This document is source-only. It does not authorize GitHub App creation or permission changes, credential placement, host installation, systemd/sudo/root changes, production deployment, database writes, Cloudflare changes, or any other live mutation.

Repository-local deployment contracts remain stricter where applicable. Merge never authorizes deployment.

## 2. Architecture decision

The intended control flow is:

```text
owner decision
  -> public-safe DEPLOY-QUEUE state in ops-workflows
  -> separate owner-authored LIVE-AUTH object in ops-workflows
  -> RPi5 outbound-only authenticated polling
  -> authorization/queue/source/CI/baseline revalidation
  -> static operation registry
  -> fixed project adapter
  -> existing narrow project controller/root helper
  -> health/evidence
```

No GitHub-controlled field may become a shell command, executable path, arbitrary argv list, Docker command, sudo command, or dynamic import target.

## 3. Program ordering

This is a cross-cutting transport/security track, not a replacement for the ordered migration phases in `AUTOMATION_MASTER_PLAN.md`.

- P0-P5 may prepare and prove source-only contracts when explicitly selected by the owner and when they do not perform host/runtime/permission mutation.
- Source work in this track must not silently consume or supersede a repository-specific authorization or the current Hermes Deals Phase 4 execution lane.
- P6 merge remains explicit owner authority.
- P7 and later live steps are blocked until the master plan separately names the exact live step as eligible and the owner gives the required explicit authorization.

## 4. Trust domains

### 4.1 Owner identity

The configured owner authority is the GitHub user with numeric ID `277435981`.

The numeric ID is authoritative. Login text is display-only because logins can be renamed. A valid owner actor must also be returned by GitHub as `type=User`.

Compromise of the owner's GitHub account is equivalent to compromise of the owner authorization boundary and is outside what this protocol can cryptographically distinguish. Account security therefore remains a prerequisite.

### 4.2 ChatGPT/GitHub operator path

ChatGPT may prepare a LIVE-AUTH request only after the owner gives an explicit live/deploy instruction that satisfies the repository's governing authorization contract.

The GitHub mutation that creates LIVE-AUTH is itself part of the live authorization transport. Generic `START`, `turpini`, merge approval, GITHUB-ONLY, a READY queue item, or prior authorization must never create LIVE-AUTH.

P9 must prove that the actual connected GitHub write path creates the LIVE-AUTH object with GitHub server metadata identifying the configured owner numeric user ID. If GitHub reports a bot/app actor instead, the protocol fails closed and the authorization transport must be redesigned before production enablement.

### 4.3 `ops-workflows` authorization store

`ops-workflows` stores public-safe queue and authorization metadata. It must never contain credentials, protected host paths, private runtime configuration, secret material, raw private evidence, or arbitrary executable commands.

A READY deploy queue item means eligible for consideration only. It is not live authorization.

### 4.4 Deploy authorization reader credential

Critical invariant:

**No credential held by the autonomous RPi5 executor may have permission to modify the GitHub surface from which owner authorization is accepted.**

The first live GitHub App for this protocol therefore defaults to:

- installation scope: `rozkalnsandris/ops-workflows` only;
- Issues: read-only;
- Metadata: minimum/implicit read;
- all write permissions: no access;
- webhook: disabled.

The previously proposed single App with `Issues: read/write` is rejected by this threat model because GitHub documents that `Issues: write` can update issue comments and issue state/content surfaces. A credential that can rewrite authorization material cannot also be trusted to validate that material as owner-authored.

If automated GitHub result reporting is added later, its write capability must be separated from the accepted authorization surface. Acceptable future designs include a distinct repository/surface or a separately reviewed narrow reporting mechanism. The reporter must not be able to create, edit, delete, relabel, close, reopen, or otherwise forge accepted LIVE-AUTH authority.

Until that separation is proven, local durable evidence plus the existing approved notification path is preferred over granting the executor GitHub write authority.

### 4.5 Existing `Rozkalns Automation` App

The existing App remains unchanged and read-only:

- Actions: read;
- Contents: read;
- existing approved repository installation scope only.

It remains the source/CI truth reader for repositories already in its contract. This executor work must not opportunistically add Issues write, workflow write, deployments write, repository administration, or additional repository scope to that App.

### 4.6 Unprivileged poller

The always-on poller:

- runs without root;
- has no generic sudo path;
- should retain `NoNewPrivileges=true`;
- performs only outbound HTTPS to GitHub and local trusted-controller IPC/state operations;
- accepts only structured GitHub data;
- never resolves `operation_id` into a shell string.

A compromised poller may at most submit a bounded request identity to the privileged dispatcher. That alone must never be sufficient to mutate production.

### 4.7 Privileged dispatcher

The privileged dispatcher independently re-resolves the accepted request and static operation registry immediately before entering a mutation-capable adapter.

It accepts only a narrow identifier, such as repository identity plus LIVE-AUTH issue ID/request ID. It does not accept target SHA, shell argv, executable paths, rollback commands, or mutation budgets as trusted parameters from the unprivileged poller.

### 4.8 Project adapter/root helper

Each operation is implemented by a reviewed fixed adapter that delegates to an existing project-specific controller/helper where possible. The adapter must preserve that project's stricter exact-SHA, deploy-classification, locking, transaction, health, rollback and evidence rules.

There is no generic deploy adapter.

## 5. Authorization object v1

### 5.1 Transport

A live authorization is one normal GitHub Issue in `rozkalnsandris/ops-workflows` with title:

```text
[LIVE-AUTH][PENDING] <public-safe target alias>
```

The issue must not be a pull request.

### 5.2 Fixed TTL

Protocol v1 TTL is exactly **600 seconds (10 minutes)** from GitHub server `created_at`.

TTL is not caller-selectable and is not extended by edits, comments, labels, reactions, retries, polling delays or local restarts.

The executor should compare `created_at` with the GitHub HTTP response `Date` header from the authenticated fetch. If the server time is unavailable, malformed, earlier than `created_at` beyond a small documented tolerance, or more than 600 seconds after creation, mutation-capable execution fails closed.

### 5.3 Machine payload

The issue body contains exactly one marked JSON payload:

```text
<!-- rozkalns-live-auth:v1 -->
```json
{ ... }
```
<!-- /rozkalns-live-auth:v1 -->
```

The parser must reject missing markers, multiple payload blocks, duplicate JSON keys, non-object roots, unknown top-level fields, type mismatches, oversized values, invalid Unicode, or trailing second authority blocks.

Required fields:

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
    {
      "category": "reviewed-category-id",
      "max_operations": 1
    }
  ],
  "rollback_policy": "NONE",
  "exclusions": ["explicit exclusion"],
  "dependencies": []
}
```

`operation_id`, mutation categories, rollback policies and baseline resolver IDs are enums owned by source-controlled RPi5 policy. GitHub may select only already-existing values; it cannot define new executable behavior.

### 5.4 Canonical payload digest

After strict JSON parsing, calculate a semantic digest over UTF-8 JSON serialized with:

- object keys sorted lexicographically;
- separators exactly `,` and `:` with no insignificant whitespace;
- JSON strings encoded normally without ASCII-only coercion;
- duplicate keys already rejected before serialization.

Conceptually this is equivalent to Python:

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

Store `SHA-256(canonical_payload)` plus a separate SHA-256 of the exact raw issue body observed at acceptance.

Immediately before privileged dispatch, re-fetch the issue and require both digests to remain identical.

## 6. Acceptance algorithm

A request is eligible only when all checks pass in order:

1. repository identity is exactly `rozkalnsandris/ops-workflows`;
2. resource is an Issue, not a PR;
3. issue is open;
4. title matches the supported LIVE-AUTH v1 form;
5. GitHub `user.id == 277435981` and `user.type == User`;
6. GitHub server time proves `0 <= age <= 600 seconds` within the documented clock tolerance;
7. strict payload parser passes;
8. `request_id` and GitHub issue ID are unseen in local durable state;
9. referenced queue issue is open and exactly READY;
10. queue source repo/SHA/target/operation/mutation envelope matches LIVE-AUTH;
11. exact source SHA exists and is still allowed by repository-local policy;
12. required exact-SHA CI/review evidence is fresh and successful;
13. expected target baseline still matches or its reviewed resolver returns the expected state;
14. static operation registry contains the exact operation and permits the declared deploy class/mutation budget/rollback policy;
15. required adapter/helper identities and cross-repository interfaces are proven;
16. no new secret, permission, DB, infrastructure or undeclared mutation is required;
17. immediately before privileged dispatch, repeat the GitHub authorization, queue, source/CI and baseline reads and require the accepted body/payload digests unchanged.

Unknown or incomplete evidence is rejection, not permission.

## 7. Replay and local state

Use a durable trusted local store; SQLite is the preferred first implementation unless P1 review proves a simpler equivalent has the same crash/replay properties.

Minimum unique identities:

- GitHub repository ID + issue ID;
- `request_id`.

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

`CONSUMED` must be persisted atomically **before** crossing into a mutation-capable adapter/IPC request. Entry into that boundary consumes authorization even if the adapter later discovers that its first intended external write cannot start. False-positive consumption is preferred over replay.

A process crash after `CONSUMED` must never replay automatically. Recovery requires evidence and a new owner authorization unless a repository-local contract explicitly proves a non-mutating pre-write state and separately defines a safe recovery path.

## 8. Polling and GitHub API contract

Webhooks remain disabled because no inbound RPi5 listener is required.

When polling is used:

- authenticated requests only;
- fixed interval, initially approximately 2 minutes;
- requests serialized rather than concurrent;
- stable/specific query URLs;
- retain `ETag` and use `If-None-Match` where supported;
- honor `Retry-After` and `X-RateLimit-*`;
- no busy retry on primary or secondary rate limiting;
- bounded pre-mutation transport retry only;
- no GitHub write retry after mutation-capable execution begins.

GitHub documents that correctly authorized conditional GETs returning `304 Not Modified` do not consume the primary REST rate limit.

Pin one supported REST API version in source. At implementation time, re-check the current GitHub documentation rather than hard-coding a historical API version from this document.

## 9. Operation registry contract

The registry is source-controlled under `RPi5_main` and is the only mapping from GitHub data to executable behavior.

Every operation record must define:

- schema/version;
- operation ID;
- source repository;
- target alias/class;
- allowed deploy classification;
- fixed adapter identity;
- required source/CI evidence;
- allowed mutation categories and maximum counts;
- rollback policy enum;
- postconditions;
- LIVE-ALL eligibility class;
- cross-repository contract/version IDs.

Forbidden registry features:

- shell snippets;
- arbitrary argv arrays from GitHub;
- user-controlled executable paths;
- environment injection from GitHub;
- dynamic Python/module imports from GitHub values;
- generic `sudo`, Docker or systemctl passthrough.

Unknown operation IDs fail closed.

## 10. Rollback semantics

The global rule remains: after authorized mutation begins, error or ambiguity means evidence plus STOP; do not retry, clean up, select an alternate path or roll back unless that exact behavior was pre-authorized.

Therefore an adapter may invoke a project helper with built-in rollback only when all of these are true:

1. the registry names a reviewed rollback policy ID;
2. LIVE-AUTH names the identical rollback policy;
3. the queue envelope names the same rollback behavior;
4. the helper's exact source/installed identity is revalidated;
5. rollback scope and operation counts are bounded;
6. tests prove no alternate/unbounded rollback path.

`rollback_policy=NONE` forbids automatic rollback, even if a generic helper would otherwise attempt one. Such a helper is not eligible until an adapter can enforce the declared policy.

## 11. Threat model

| Threat | Required defense |
| --- | --- |
| Executor bot forges owner approval | Executor credential is read-only on authorization surface; exact numeric owner actor required |
| App edits owner issue/comment then executes it | No executor Issues write permission on authorization repository |
| Stale authorization executes later | Fixed 600-second GitHub-server-time TTL |
| Edited authorization | Raw body + canonical payload digests re-fetched immediately before dispatch |
| Replay after success/failure/crash | Durable unique issue/request IDs; atomic `CONSUMED` before privileged boundary |
| Queue changed after approval | Fresh queue revalidation immediately before dispatch |
| Source/main changed | Exact immutable SHA binding; repository-local reachability/current-main rules revalidated |
| CI evidence changed/missing | Exact-SHA Actions read and required job/check semantics revalidated |
| Target baseline drift | Exact baseline/resolver re-run immediately before mutation |
| Malicious `operation_id` | Static allowlisted registry; unknown values reject |
| Arbitrary shell/path injection | GitHub has no command/path/argv authority; adapters are fixed source code |
| Poller compromise | No generic sudo; privileged dispatcher independently revalidates request |
| Dispatcher confused-deputy attack | Dispatcher accepts only narrow request identity and re-reads authority itself |
| GitHub partial outage/ambiguous response | Fail closed before mutation; no cached permission decision substitutes for fresh evidence |
| Rate limiting | Conditional GET, serialized requests, obey retry headers, hard retry ceiling |
| Local state loss/corruption | Mutation path disabled until durable state integrity is restored; never assume unseen/replay-safe |
| Helper identity drift | Exact source/installed identity and cross-repo contract revalidation |
| Helper failure after mutation | Evidence + STOP; only explicitly authorized built-in rollback may run |
| Result-report write fails after successful deploy | Production result remains authoritative from local health/evidence; no retry that could repeat deployment; reporting reconciled separately |
| Public issue leaks sensitive data | Public-safe schema only; secrets/private paths/protected config rejected from evidence |
| Owner GitHub account compromise | Out of protocol scope; treat as owner-boundary compromise and rely on GitHub account security/revocation |

## 12. Result reporting separation

P0 intentionally does not grant an autonomous GitHub write credential.

Local evidence must record the final request ID, source SHA, target, operation ID, consumed state, mutation counts, health/postcondition result and sanitized failure class.

A later phase may add automatic GitHub receipts only after proving that the reporter cannot mutate the accepted authorization store. Result-write failure must never cause the deployment operation to run again.

## 13. First canary rules

- No dummy commit, placeholder deployment or invented production delta solely to exercise automation.
- P9 uses the first genuine prepared owner decision to prove the complete path in dry-run/mutation-disabled mode.
- P10 uses the lowest-risk genuine READY ordinary deployment available at that time.
- High-risk control-plane operations such as Hermes Tech pull-deploy activation are deferred until the ordinary canary is proven.

## 14. External documentation reviewed for P0

Reviewed 2026-08-27 against current official documentation:

- GitHub REST API best practices: authenticated requests, serialized polling, conditional requests, `Retry-After`, bounded rate-limit handling;
- GitHub App installation authentication: installation tokens expire after one hour and can be scoped down to selected repositories/permissions within the App installation grant;
- GitHub Issues/Issue Comments permissions: `Issues: write` is sufficient for update operations, which is why the executor credential must not have write permission on the accepted authorization surface;
- GitHub reaction APIs identify the reacting user, but reactions are not used as the primary v1 authorization binding because an issue payload remains mutable to any credential with Issues write.

Re-check these contracts immediately before P2/P7 because GitHub API versions and product semantics can change.

## 15. P0 exit gate

P0 is complete only when:

- this threat model is reviewed in a focused PR;
- `AUTOMATION_MASTER_PLAN.md` explicitly records this as a cross-cutting source-only track without changing the current Phase 4 live ordering;
- issue #236 is reconciled with the read-only authorization-reader invariant;
- no GitHub App permission, host, credential, systemd, sudo/root, production or Cloudflare mutation occurred.

After P0 reaches Ready, STOP for explicit merge decision. Do not start P1 under the P0 authorization.