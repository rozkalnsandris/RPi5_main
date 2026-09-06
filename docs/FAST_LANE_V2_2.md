# FAST-LANE v2.2 Composite — RPi5_main

This is the active local FAST-LANE startup contract. The older versioned filename is retained only for backward compatibility and is not startup authority.

## Core rule

**The human approves the RISK / DECISION. Automation executes the TECHNICAL STEPS.** Read-only checks never create owner gates. STRICT describes host/runtime mutation risk, not approval-per-command.

## Lane role

FAST-LANE is the **safe discovery, audit and non-FULL continuation lane**. It is the correct default for `START`, `turpini`, ambiguous scope, audits, diagnosis and work that should stop at a human decision boundary.

For a concrete implementation issue with a usable Definition of Done, the preferred implementation lane is the separately explicit `AUTO-RUN FULL RPi5_main #<issue>` contract in `.github/auto-run-full-v2.json` and `docs/AUTO_RUN_FULL_V2.md`.

FAST never infers AUTO-RUN FULL authority.

## Command routing invariant

Bare `START`, `START RPi5_main`, `SYNC RPi5_main`, `turpini`, or equivalent continuation selects normal **FAST-LANE v2.2** operation. It does **not** select `GITHUB-ONLY` or `AUTO-RUN FULL`.

`GITHUB-ONLY` is active only when the owner explicitly includes the `GITHUB-ONLY` mode in the current command (including the documented `git hub only` spelling). `LIVE-ALL` likewise requires an explicit current-command `LIVE-ALL` token.

`AUTO-RUN FULL` is a separate explicit issue-scoped implementation mode and is active only from the exact command form `AUTO-RUN FULL RPi5_main #<issue>`. Its local contract is `.github/auto-run-full-v2.json` plus `docs/AUTO_RUN_FULL_V2.md`.

Never infer an explicit mode from `.github/start-github-only.json`, a deploy queue, a handoff/issue, controller state, executor availability, historical chat state, or a prior authorization receipt. Those are state/evidence inputs after command mode has been selected; they are not mode selectors. The machine-readable local dispatcher contract is `.github/start-mode-routing.json`.

## Outcome delivery default

Read `.github/outcome-delivery-v1.json` and `docs/OUTCOME_DELIVERY_V1.md` for the active repository-local packaging and merge-convergence contract.

Default source delivery is **one visible outcome issue -> one outcome branch -> one Outcome PR**. Batch 2-5 closely related same-risk work items and include the implementation, wiring/integration, tests, operator/preflight and docs/provenance needed to make that outcome independently useful and testable.

Do not split work merely at an internal layer or proof-object boundary. Split only when the result is independently valuable, crosses a different risk/trust boundary, changes runtime target/owner decision, or would otherwise stop being one coherent review unit.

Native GitHub stacked PRs are not the current RPi5_main default. GitHub stack maintenance requires linear history and cascading rebases; GitHub CLI stack push uses force-with-lease, while this repository forbids force-push/history rewrite. GitHub also does not currently support auto-merge for stacked PRs. Enabling stacks therefore requires a separate explicit repository-policy change.

## FAST

`START`, `turpini`, or equivalent continuation may carry safe source, documentation, test and policy/orchestration work from fresh canonical GitHub state through Ready in one coherent batch when it does not read protected runtime data or mutate the host. This includes branch, PR, CI/review and up to two scope-preserving corrections. Batch 2-5 closely related same-risk items when coherent.

Use FAST to discover or define the implementation issue/DoD/risk envelope. Once that exact implementation issue exists, prefer switching to `AUTO-RUN FULL <repo> #<issue>` rather than repeatedly driving ordinary implementation with `turpini`.

Merge remains an explicit owner decision in FAST, but the owner should not have to wait for a technical CI polling boundary once the final intended diff and exact head are frozen.

## Exact-head conditional MERGE in FAST

After the final intended diff is frozen, FAST may request one explicit owner merge authorization in the exact form:

```text
MERGE RPi5_main #<pr> HEAD=<exact-head-sha>
```

The owner may grant this while required checks are still running. The authorization state is then `MERGE_AUTHORIZED_PENDING_CHECKS`; automation continues technical CI/review convergence without another owner nudge.

Before merge execution, freshly verify current `main`, PR state, exact head, final scope/diff, all required status checks, unresolved review threads and mergeability. Merge only with the repository's allowed squash method and an expected-head SHA guard (or equivalent fail-closed GitHub primitive).

Any PR head change invalidates the authorization, including a corrective commit or a base synchronization that creates a new head. Do not merge and do not silently transfer the authorization to the new SHA; request a new exact-head MERGE decision.

Do not arm GitHub auto-merge early for this SHA-bound FAST authorization. Early PR-level auto-merge is intentionally not the FAST conditional merge primitive.

## Human gate budget

Normal FAST delivery has at most two owner gates: **MERGE**, then **COMPOSITE LIVE** only when host/runtime mutation is required. CI polling, exact-SHA evidence, read-only preflight, checkout discovery, clean/ancestor validation, build preparation and reconciliation are automation steps.

`AUTO-RUN FULL` is not an implicit bypass of those gates. It is a different explicit owner decision model: the one command freezes an issue-specific authorization envelope that may include merge authority and already-declared runtime mutation classes. No additional owner message is required for actions already inside that frozen envelope, but newly discovered mutation classes or targets are outside authority.

## AUTO-RUN FULL v2 relationship

For an active, valid `AUTO-RUN FULL RPi5_main #<issue>` authorization:

- the target GitHub issue and owner-identity activation receipt are the durable work/authority record;
- the default delivery unit is one Outcome PR for that frozen issue;
- normal source/PR/CI/review corrections continue without the FAST two-correction ceiling, subject to the AUTO-RUN anti-loop ceiling;
- GitHub event-triggered ChatGPT Work is the preferred low-latency resume path for supported PR activity, while the hourly Scheduled Task remains a watchdog/fallback;
- merge may proceed only for the exact canonical PR/head after fresh required checks and review convergence;
- v2 prefers GitHub native auto-merge only after final exact-head readiness has been freshly proven and repository auto-merge capability is enabled;
- a changed head voids prior merge readiness and requires fresh review/checks before auto-merge may be enabled again;
- native stacked PRs remain disabled under the current no-history-rewrite policy;
- a turn/session ending is resumable and must persist state to GitHub;
- runtime mutation is permitted only when the activation envelope froze the exact mutation class/target and the existing reviewed executor protocol accepts it;
- AUTO-RUN never gives the conversational agent direct root/sudo/secret/protected-runtime access.

## Composite STRICT

One live authorization may cover tightly coupled operations required for one bounded host/runtime action when it binds exact Git SHA, exact host/target, allowed mutation categories, hard limits, explicit exclusions and expected baseline. A trusted local checkout may perform only explicitly allowed `git fetch` + `git merge --ff-only` inside the same envelope when needed; this never implies `reset`, `rebase`, `clean` or force operations.

A valid AUTO-RUN FULL activation may serve as that up-front live decision only for mutation categories frozen in its owner-identity activation receipt. When the existing `#236` deferred pull executor requires a short-lived LIVE-AUTH GitHub issue, AUTO-RUN may materialize it later only after fresh revalidation and only for the already-frozen target/operation class.

Preflight is the beginning of the same fail-closed one-shot. Revalidate SHA/host/baseline immediately before first mutation and stop on drift. Use pinned tooling and exact artifacts where applicable.

## Local STRICT boundaries

Sudo/root, packages, services/timers, Docker, networking/firewall/DNS/Cloudflare Tunnel, SSH/users/mounts/kernel, backups, databases/application data, secrets/credentials, protected configuration/runtime inspection or another host/runtime mutation require Composite Live authorization or an exact equivalent frozen AUTO-RUN FULL authorization. Uncertain live classification is STRICT.

AUTO-RUN FULL does not authorize the agent to run `sudo` or read protected paths. It may only drive an already-reviewed narrow executor/operation through the repository's declared authorization boundary.

## Failure and evidence

Authorization is consumed at the first authorized live mutation. Any later error/ambiguity requires evidence preservation and the retry/rollback/cleanup behavior frozen by the authorization envelope. If none was frozen, the result is STOP; do not improvise an automatic retry, rollback, cleanup, reset, rebase or alternate mutation path.

For normal FAST delivery, use one Ready receipt and one final live receipt. Put any remaining owner decision at the **end** under `ACTION REQUIRED`; when the owner must enter/run something, provide the exact copyable instruction in a fenced `bash` block.

Independently of whether an owner gate exists, every user-visible work-cycle terminal response that ends or pauses repository work must end with exactly one copy-pasteable `NEXT COMMAND`. If a real owner gate exists, `ACTION REQUIRED` contains that exact command and also satisfies the Next Command Contract. Otherwise use the state-appropriate non-gate command: `SYNC RPi5_main` while waiting for mutable CI/review/external state, `turpini` for immediate same-scope technical continuation, or `START RPi5_main` after DONE to select the next canonical lane. Never invent an owner gate to satisfy this presentation rule.

For AUTO-RUN FULL, routine technical continuation does not generate `ACTION REQUIRED`, but it still obeys the Next Command Contract. Notify the owner only on `DONE`, `STOP_SCOPE_OR_RISK`, `STOP_ERROR`, or a platform-level approval that ChatGPT itself requires; any user-visible terminal/status response still ends with one exact resume/refresh command.

Merge never by itself authorizes host/runtime mutation. AUTO-RUN FULL authority comes from the separately frozen issue-specific owner activation, not from merge.
