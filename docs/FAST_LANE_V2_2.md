# FAST-LANE v2.2 Composite — RPi5_main

This is the active local FAST-LANE startup contract. The older versioned filename is retained only for backward compatibility and is not startup authority.

## Core rule

**The human approves the RISK / DECISION. Automation executes the TECHNICAL STEPS.** Read-only checks never create owner gates. STRICT describes host/runtime mutation risk, not approval-per-command.

## Lane role

FAST-LANE is the **safe discovery, audit and non-FULL continuation lane**. It is the correct default for `START`, `turpini`, ambiguous scope, audits, diagnosis and work that should stop at a human decision boundary.

For a concrete implementation issue with a usable Definition of Done, the preferred implementation lane is the separately explicit `AUTO-RUN FULL RPi5_main #<issue>` contract in `.github/auto-run-full-v2.json` and `docs/AUTO_RUN_FULL_V2.md`.

FAST never infers AUTO-RUN FULL authority.

## Command routing invariant

Bare `START`, `START RPi5_main`, `turpini`, or equivalent continuation selects normal **FAST-LANE v2.2** operation. It does **not** select `GITHUB-ONLY` or `AUTO-RUN FULL`.

`GITHUB-ONLY` is active only when the owner explicitly includes the `GITHUB-ONLY` mode in the current command (including the documented `git hub only` spelling). `LIVE-ALL` likewise requires an explicit current-command `LIVE-ALL` token.

`AUTO-RUN FULL` is a separate explicit issue-scoped implementation mode and is active only from the exact command form `AUTO-RUN FULL RPi5_main #<issue>`. Its local contract is `.github/auto-run-full-v2.json` plus `docs/AUTO_RUN_FULL_V2.md`.

Never infer an explicit mode from `.github/start-github-only.json`, a deploy queue, a handoff/issue, controller state, executor availability, historical chat state, or a prior authorization receipt. Those are state/evidence inputs after command mode has been selected; they are not mode selectors. The machine-readable local dispatcher contract is `.github/start-mode-routing.json`.

## FAST

`START`, `turpini`, or equivalent continuation may carry safe source, documentation, test and policy/orchestration work from fresh canonical GitHub state through Ready in one coherent batch when it does not read protected runtime data or mutate the host. This includes branch, PR, CI/review and up to two scope-preserving corrections. Batch 2-5 closely related same-risk items when coherent. Merge remains explicit in FAST.

Use FAST to discover or define the implementation issue/DoD/risk envelope. Once that exact implementation issue exists, prefer switching to `AUTO-RUN FULL <repo> #<issue>` rather than repeatedly driving ordinary implementation with `turpini`.

## Human gate budget

Normal FAST delivery has at most two owner gates: **MERGE**, then **COMPOSITE LIVE** only when host/runtime mutation is required. CI polling, exact-SHA evidence, read-only preflight, checkout discovery, clean/ancestor validation, build preparation and reconciliation are automation steps.

`AUTO-RUN FULL` is not an implicit bypass of those gates. It is a different explicit owner decision model: the one command freezes an issue-specific authorization envelope that may include merge authority and already-declared runtime mutation classes. No additional owner message is required for actions already inside that frozen envelope, but newly discovered mutation classes or targets are outside authority.

## AUTO-RUN FULL v2 relationship

For an active, valid `AUTO-RUN FULL RPi5_main #<issue>` authorization:

- the target GitHub issue and owner-identity activation receipt are the durable work/authority record;
- normal source/PR/CI/review corrections continue without the FAST two-correction ceiling, subject to the AUTO-RUN anti-loop ceiling;
- GitHub event-triggered ChatGPT Work is the preferred low-latency resume path for supported PR activity, while the hourly Scheduled Task remains a watchdog/fallback;
- merge may proceed only for the exact canonical PR/head after fresh required checks and review convergence;
- v2 prefers GitHub native auto-merge only after final exact-head readiness has been freshly proven and repository auto-merge capability is enabled;
- a changed head voids prior merge readiness and requires fresh review/checks before auto-merge may be enabled again;
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

For AUTO-RUN FULL, routine technical continuation does not generate `ACTION REQUIRED`. Notify the owner only on `DONE`, `STOP_SCOPE_OR_RISK`, `STOP_ERROR`, or a platform-level approval that ChatGPT itself requires.

Merge never by itself authorizes host/runtime mutation. AUTO-RUN FULL authority comes from the separately frozen issue-specific owner activation, not from merge.
