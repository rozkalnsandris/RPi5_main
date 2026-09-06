# AUTO-RUN FULL v2 — event-driven issue-to-DONE orchestration

Status: **ACTIVE**

Canonical machine contract: `.github/auto-run-full-v2.json`
Outcome packaging contract: `.github/outcome-delivery-v1.json` and `docs/OUTCOME_DELIVERY_V1.md`
Roadmap: `RPi5_main#315`
Durable controller state: `RPi5_main#295`
Runtime/deferred execution dependency: `RPi5_main#236`

## Operating model

`AUTO-RUN FULL` is the normal implementation lane. `FAST-LANE v2.2` remains the safe discovery, audit and non-FULL continuation lane.

The owner starts implementation with one explicit issue-scoped command:

```text
AUTO-RUN FULL RPi5_main #<issue>
```

That command freezes one authorization envelope for the exact open issue. It is not blanket repository authority and is never inferred from `START`, `turpini`, controller state, chat history or a prior run.

The default source delivery unit is one visible outcome:

```text
one frozen outcome issue
  -> one outcome branch
  -> 2-5 closely related same-risk work items
  -> one Outcome PR
  -> CI + review convergence
  -> guarded exact-head merge
  -> post-merge verification
  -> DONE
```

Routine source analysis, edits, tests, branch/commit/push, PR creation/update, CI inspection, focused corrections, review ingestion and ordinary merge-conflict correction are technical steps rather than new owner gates.

## Outcome Delivery v1 relationship

Read `.github/outcome-delivery-v1.json` and `docs/OUTCOME_DELIVERY_V1.md`.

AUTO-RUN FULL should optimize for the issue's **observable Definition of Done**, not for small PR count. Keep small logical commits inside the Outcome PR, but include implementation, wiring/integration, tests, operator/preflight and docs/provenance together when they are required to make the same outcome independently useful and testable.

Split into a separate issue/PR only when the work is independently valuable, crosses a different risk/trust boundary, targets a different runtime/owner decision, or would otherwise stop being one coherent review unit.

Native GitHub stacked PRs are not used by default in `RPi5_main`. Current GitHub stack maintenance relies on linear-history rebases and force-with-lease branch updates, which conflicts with this repository's no-force/no-history-rewrite policy. GitHub also does not currently support auto-merge for stacked PRs. A future stack workflow therefore requires a separate explicit repository-policy change.

## FAST-LANE relationship

Bare `START RPi5_main`, `START`, `turpini` or equivalent continuation remains `FAST-LANE v2.2`.

FAST is used when the implementation issue or risk envelope is not yet sufficiently defined, for audits/discovery, and for safe continuation that should stop at a decision boundary. FAST never infers AUTO-RUN FULL authority and never inherits merge/live authority from a previous FULL run.

Once a concrete implementation issue with a usable Definition of Done exists, the preferred operator command is `AUTO-RUN FULL RPi5_main #<issue>`.

## Durable state and resume architecture

GitHub is the canonical state and authorization plane. The target issue, activation receipt, controller issue, canonical Outcome PR and current GitHub checks/reviews are re-read before state-dependent actions.

V2 uses two resume paths:

1. **Primary: GitHub event-triggered ChatGPT Work task.** Supported pull-request activity can resume work with low latency after PR open/ready, review/comment, commit update or completed merge events.
2. **Fallback: hourly ChatGPT Scheduled watchdog.** The existing `RPi5 AUTO-RUN` task remains active so lost/grouped events, inactivity or product limitations do not lose durable work. It reconstructs the controller from GitHub and resumes only the already-active frozen issue.

The event-triggered path is an accelerator, not a separate authority source. If it is unavailable, correctness falls back to the hourly watchdog or a manual `turpini` resume.

Current OpenAI platform limits reviewed for v2: eligible paid scheduled tasks can recur up to once per hour; event-triggered tasks can run up to 30 times per hour across event-triggered tasks. Connected-app approval and plan/workspace limits still apply.

## Activation transaction

Before activation, freshly read:

1. `AGENTS.md`;
2. `.github/start-mode-routing.json`;
3. `.github/auto-run-full-v2.json`;
4. `.github/outcome-delivery-v1.json`;
5. the exact target issue and Definition of Done;
6. current `main`;
7. active PR/CI/review state;
8. relevant dependencies/continuity;
9. controller issue `#295`.

Activation fails closed if another issue is active.

Materialize an owner-identity activation receipt using schema:

```text
rozkalns.auto-run-full-authorization.v2
```

The receipt freezes repository, issue, Definition of Done, allowed source actions, merge authority, any already-declared runtime mutation classes/targets, retry/rollback semantics and explicit exclusions. Later issue edits may reduce or clarify scope but never silently add authority.

## Source convergence loop

Each worker run makes the maximum coherent progress supported by fresh GitHub evidence:

1. refresh issue/controller/current main/canonical Outcome PR;
2. confirm the one-outcome delivery slice and next action inside frozen scope;
3. implement the coherent source slice, keeping small logical commits inside the same Outcome PR;
4. validate and inspect the integrated diff;
5. commit exact paths and push;
6. create/update the canonical Outcome PR;
7. inspect required CI and review state;
8. correct branch-caused failures or actionable findings without scope expansion;
9. repeat until exact-head source/review/CI convergence;
10. perform the final exact-head merge gate;
11. use GitHub auto-merge when repository capability is enabled and the exact head is already fully ready;
12. verify exact post-merge `main` and Definition of Done;
13. continue only into runtime/live classes already frozen by activation;
14. write terminal receipt and return controller to `IDLE`.

Three materially identical failed attempts without a materially new safe hypothesis produce `STOP_ERROR`.

Do not open a new dependent PR merely to isolate an internal proof object. A corrective commit remains on the canonical Outcome PR unless the correction reveals genuinely new scope/risk.

## Guarded GitHub auto-merge

V2 may use GitHub native auto-merge, but **does not arm it early on an unreviewed, CI-pending mutable head merely to save polling time**.

Before enabling auto-merge for the canonical Outcome PR, all of the following must be freshly true for the exact current head:

- the target issue and latest activation receipt still match;
- the PR is the canonical implementation for the frozen issue;
- exact head SHA is freshly read;
- final diff/scope review is complete;
- required CI is green;
- unresolved actionable review findings are zero;
- current mergeability is acceptable;
- repository ruleset requirements are satisfied;
- no force/history rewrite or scope expansion is needed.

Only then may the worker enable GitHub auto-merge for that exact canonical PR. GitHub remains responsible for enforcing repository merge requirements; AUTO-RUN never bypasses rulesets.

A changed head invalidates the prior readiness decision. The new head must be freshly reviewed and checked before auto-merge may be enabled again.

If repository auto-merge is unavailable, the existing direct exact-head merge path is a fallback only after the same final readiness gate and only when the frozen FULL activation already supplies merge authority. When a direct merge primitive supports an expected-head SHA precondition, use it.

GitHub auto-merge is not used for native stacked PRs because GitHub currently does not support auto-merge for stacked pull requests.

### Repository setup gate

GitHub requires `Allow auto-merge` to be enabled in repository settings before per-PR auto-merge can be used. The repository currently exposes that capability. Enabling or retaining auto-merge must not weaken branch/ruleset protections.

## Ruleset invariant

Do not trade safety checks for throughput.

`main` remains governed by the repository ruleset, including pull-request delivery, squash-only merge, linear history, required review-thread resolution and strict required status checks. AUTO-RUN may reduce waiting by batching a coherent outcome and resuming automatically, but it must not bypass or remove required checks.

Strict checks may require a new head/check run after base drift. Any changed head invalidates previous exact-head readiness.

## Runtime/live boundary

AUTO-RUN FULL is not arbitrary root, sudo, secret or infrastructure authority.

For `RPi5_main`, the up-front command may cover live execution only for exact mutation classes and targets frozen before the first live mutation and only through existing reviewed repository executor protocols. `#236` remains the deterministic GitHub-to-RPi5 execution trust boundary where applicable.

New secret/credential/permission/trust-boundary classes, undeclared DB/infrastructure mutation, a different production target or another unbound live operation produce `STOP_SCOPE_OR_RISK`.

After source merge and exact-main verification, one bounded Composite LIVE may cover tightly coupled runtime steps only if those mutation classes/targets were frozen by the active authorization model and accepted by the reviewed executor protocol.

After a live mutation starts, recovery follows only retry/rollback/cleanup semantics already frozen by authorization. Otherwise an error or ambiguous result is `STOP_ERROR`; no improvisational retry, rollback, cleanup or alternate mutation path.

Merge never authorizes LIVE.

## Controller states

```text
IDLE
ACTIVATING
WORKING
WAITING_CI
WAITING_REVIEW
CORRECTING
WAITING_EVENT_RESUME
WAITING_WATCHDOG_RESUME
PAUSED_USAGE
PAUSED_PLATFORM_APPROVAL
PAUSED_EXTERNAL
VERIFYING
DONE
STOP_SCOPE_OR_RISK
STOP_ERROR
```

A turn ending, CI waiting or review waiting is not an owner gate. Persist state and resume from GitHub.

## Billing and model boundary

V2 remains ChatGPT Plus first:

- no `OPENAI_API_KEY`;
- no provider LLM API keys;
- no token-billed fallback;
- no automatic paid-credit purchase;
- Codex and Copilot are optional, not correctness dependencies.

If product usage is exhausted, persist `PAUSED_USAGE`; do not silently change billing mode.

## Terminal behavior

Normal terminal state is `DONE` only after current evidence proves the target Definition of Done, exact post-merge main is verified, any authorized runtime work is verified, a final GitHub receipt is written and controller `#295` returns to `IDLE`.

Notify the owner for `DONE`, `STOP_SCOPE_OR_RISK`, `STOP_ERROR` or a platform-level approval that requires owner action. Routine implementation progress does not require owner nudges.
