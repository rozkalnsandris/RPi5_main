# AUTO-RUN FULL v1 — ChatGPT Plus issue-to-DONE orchestration

Status: PROPOSED SOURCE CONTRACT — activates only after merge
Canonical machine contract: `.github/auto-run-full-v1.json`
Roadmap: `RPi5_main#294`
Durable controller state: `RPi5_main#295`
Runtime/deferred execution dependency: `RPi5_main#236`

## Goal

The owner uses one command in a new ChatGPT Plus chat:

```text
AUTO-RUN FULL RPi5_main #301
```

That command is intended to be the single up-front owner authorization for the exact referenced issue. Automation then continues through the issue's declared Definition of Done without routine intermediate owner nudges.

Normal technical steps are not separate owner gates: source analysis, edits, tests, branch/commit/PR work, CI waits and corrections, review findings, ordinary merge-conflict correction, merge of the exact converged PR, post-merge verification, and only the runtime/live operations already frozen into the issue-specific authorization envelope.

The mode is issue-scoped, not repository-wide blanket authority.

## Why GitHub is the durable control plane

A ChatGPT turn, Work run, or scheduled run is not the lifetime of the task. The target GitHub issue plus the controller issue are the persistent state.

Every worker run starts by re-reading current GitHub state. Chat history and memory may help orientation but are never sufficient authority for a mutable action.

A turn/session ending is therefore a scheduling event, not project failure:

```text
WORKING -> WAITING_SCHEDULED_RESUME -> next ChatGPT run -> WORKING
```

## Platform model validated against current OpenAI documentation

ChatGPT Scheduled Tasks on eligible paid plans can recur up to once per hour, can use supported connected apps including GitHub, can use information from previous runs, and can stop on a defined end condition. Connected-app approval requirements still apply; a task that needs an approval pauses until the user reviews it.

GitHub event-triggered Work tasks are an optional accelerator for supported pull-request activity. They are not the canonical state store and are not required for v1.

The AUTO-RUN design therefore assumes:

- one hourly ChatGPT Plus Scheduled Task as the persistent resume controller;
- normal ChatGPT + GitHub app actions as the primary worker surface;
- GitHub Actions as the deterministic test/build/CI execution surface;
- optional Work PR triggers only as latency reduction, never as required authority;
- no provider LLM API key and no automatic paid-credit fallback.

External references reviewed for this contract:

- OpenAI Help: `Scheduled tasks in ChatGPT`;
- OpenAI Help: `ChatGPT Work and Codex`;
- OpenAI Help: `Apps in ChatGPT` / app permissions;
- OpenAI Help: `Connecting GitHub to ChatGPT`.

## Command routing

`AUTO-RUN FULL` is valid only in the explicit form:

```text
AUTO-RUN FULL RPi5_main #<positive issue number>
```

It is never inferred from:

- `START`;
- `turpini`;
- roadmap continuity;
- a prior AUTO-RUN run;
- controller state;
- a deploy queue;
- a prior merge/live authorization;
- chat history or memory.

`turpini` during an already active AUTO-RUN task is only an immediate resume trigger. It does not create or broaden authority.

## Activation transaction

Before changing state, the activating worker must freshly read:

1. `AGENTS.md`;
2. `.github/start-mode-routing.json`;
3. `.github/auto-run-full-v1.json`;
4. the exact target issue;
5. current `main` and active PR/CI/review state;
6. relevant dependencies and canonical continuity;
7. controller issue `#295`.

Activation fails closed if another issue is already active.

The worker then materializes an owner-identity GitHub comment on the target issue using schema:

```text
rozkalns.auto-run-full-authorization.v1
```

The activation receipt freezes the authorization envelope. At minimum it records:

- exact repository and issue;
- the issue Definition of Done used for the run;
- allowed source actions;
- merge authority;
- allowed runtime mutation classes and targets, if any;
- retry/rollback policy;
- explicit exclusions.

Later edits to the issue may reduce or clarify work but never silently add mutation authority to the frozen activation. A genuinely new mutation class produces `STOP_SCOPE_OR_RISK`.

After activation, controller issue `#295` becomes the single active-task pointer.

## Source convergence loop

While the target issue is not DONE, each worker performs the maximum coherent safe progress available in the current run:

1. refresh target issue, current branch/PR and repository rules;
2. select the next action from current GitHub evidence;
3. make the smallest coherent source change;
4. run/inspect relevant validation;
5. inspect the diff/scope;
6. commit exact paths and push;
7. create/update the PR;
8. wait for or inspect CI;
9. diagnose branch-caused failures;
10. apply focused corrections;
11. ingest actionable review findings;
12. repeat until the PR converges;
13. merge only when the exact current head satisfies the frozen authorization and required checks;
14. refresh exact post-merge `main` state;
15. continue into only the live/runtime classes already frozen by the activation envelope;
16. verify final Definition of Done and write the terminal receipt.

There is no arbitrary fixed two-correction limit in AUTO-RUN FULL. Anti-loop protection is failure-fingerprint based: three materially identical failed attempts without a new safe hypothesis is terminal `STOP_ERROR`.

## Merge semantics

The explicit command itself is the owner's merge decision for the referenced issue. No later literal `MERGE` message is required when all of these remain true:

- target issue and activation receipt still match;
- current PR is the canonical implementation for that issue;
- exact head SHA is freshly re-read;
- required CI is green;
- actionable unresolved review findings are zero;
- merge does not introduce scope outside the frozen issue envelope;
- no force/history rewrite is needed.

A changed PR head invalidates old readiness evidence and requires fresh checks, but it does not require a new owner message if the new head remains inside the same frozen issue authorization.

## Runtime/live semantics

`AUTO-RUN FULL` is not arbitrary production authority.

The command may cover live execution only when the activation receipt can freeze the already-declared target and mutation class before the first live mutation. Existing reviewed operation registries, deploy-queue contracts, exact target/baseline checks, and `#236` LIVE-AUTH protocol remain the execution boundary.

When `#236` requires an owner-authored LIVE-AUTH GitHub issue, the AUTO-RUN worker may materialize that issue only if:

- the original AUTO-RUN activation already froze that live mutation class and target;
- fresh source/CI/queue/target/baseline checks still pass;
- the GitHub action is performed through the connected owner account so GitHub server metadata identifies the owner actor;
- the request is exact-SHA, TTL-limited and replay-safe under the existing LIVE-AUTH protocol.

AUTO-RUN never creates new arbitrary SSH/sudo/shell authority and never widens an executor merely to avoid an owner interaction.

## Mutation failure rule

Before the first mutation, drift is fail-closed and may be corrected only if correction remains within the frozen envelope.

After a live mutation-capable operation starts, an error or ambiguity follows the pre-authorized retry/rollback policy. If the frozen envelope did not explicitly authorize a retry/rollback/cleanup/alternate path, the result is:

```text
STOP_ERROR
```

No automatic improvisation is allowed across a trust boundary.

## Controller state machine

Externally visible states are:

```text
IDLE
ACTIVATING
WORKING
WAITING_CI
WAITING_REVIEW
CORRECTING
WAITING_SCHEDULED_RESUME
PAUSED_USAGE
PAUSED_PLATFORM_APPROVAL
PAUSED_EXTERNAL
VERIFYING
DONE
STOP_SCOPE_OR_RISK
STOP_ERROR
```

Routine CI/review/merge-conflict work does not require owner approval.

`PAUSED_PLATFORM_APPROVAL` means ChatGPT/app policy itself requires an approval that repository policy cannot suppress. The controller persists exact state and resumes after the platform permits the action. This is a product constraint, not a lost task.

## Scheduled controller

One recurring ChatGPT Plus Scheduled Task is used for all sequential RPi5_main AUTO-RUN jobs.

Every hourly run:

1. read controller issue `#295`;
2. if state is `IDLE`, do nothing and do not notify;
3. otherwise read the referenced target issue and activation receipt;
4. refresh repository/PR/CI/review state;
5. execute the maximum coherent work allowed by the frozen envelope;
6. persist the new state/evidence back to GitHub;
7. notify only on `DONE`, `STOP_SCOPE_OR_RISK`, `STOP_ERROR`, or a platform approval that needs the owner.

A user message `turpini` may trigger the same worker logic immediately instead of waiting for the next hourly run.

## Billing and model constraint

V1 is explicitly ChatGPT Plus first:

- no `OPENAI_API_KEY`;
- no Anthropic/Google/provider LLM API key;
- no token-billed fallback;
- no automatic purchase of paid credits;
- Codex is optional and not required for correctness;
- GitHub Copilot is optional and not required.

If product usage is exhausted, persist `PAUSED_USAGE` and continue after the allowance becomes available. Do not silently change billing mode.

## Terminal behavior

The normal final state is only:

```text
DONE
```

At DONE:

- the target issue's declared Definition of Done is proven from current evidence;
- final GitHub receipt identifies relevant PR/merge/runtime results without secrets;
- controller issue `#295` returns to `IDLE`;
- the owner may start the next issue with a new explicit command.

Example:

```text
AUTO-RUN FULL RPi5_main #302
```

## Scope stops

`STOP_SCOPE_OR_RISK` is reserved for a real authorization-envelope problem such as:

- a new secret/credential/permission/trust-boundary class;
- an undeclared DB or infrastructure mutation;
- a different production target;
- unrelated repository/issue work;
- an operation that cannot be bound deterministically before mutation.

Session expiration, CI waiting/failure, review findings, ordinary corrective commits and merge conflicts are not scope stops.
