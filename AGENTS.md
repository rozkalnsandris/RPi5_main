# RPi5_main agent rules

These rules are durable instructions for Codex and every other agent.

## Production safety boundary

- Work inside this repository unless a task explicitly allows a narrowly scoped, read-only inspection.
- Never obtain autonomous root access or run `sudo`.
- Do not change production configuration without a separate task that identifies the exact target and rollback.
- Do not install, remove, or upgrade packages; alter services, timers, Docker, networking, firewall, DNS, Cloudflare Tunnel, SSH, users, mounts, kernel, backups, databases, or application data.
- Do not restart, reload, stop, enable, or disable services.
- Do not read process/container environments, use `docker inspect`, or copy configuration trees.

## Forbidden paths and data

Never read, print, copy, or commit `.env` files, secrets, credentials, tokens, cookies, password stores, SSH keys or authorized-key contents, database data/dumps, backups, browser/session data, shell history, Docker volume/runtime data, or raw application configuration. In particular, do not read:

- `/home/andris/.ssh`, `/root/.ssh`, `/etc/ssh/*key*`, `/etc/ssl/private`, or `/etc/cloudflared`;
- `/var/lib/docker` or `/var/lib/postgresql`;
- Home Assistant `.storage`;
- raw Compose, systemd, cron, Nginx, Prometheus, Grafana, Cloudflare, or application configuration.

Metadata is collectable only when a task provides a strict allowlist and sanitization contract.

## Git and review workflow

- Stage exact paths only: never use `git add .`, `git add -A`, or `git add --all`.
- Inspect status and diffs, then run applicable tests before every commit.
- Push a focused branch and create a draft PR before review; never force-push.
- Do not commit generated evidence unless a future task explicitly approves a sanitized fixture.
- Never expose a secret in output, diffs, commits, PRs, or issues.

## Startup command routing

Read `.github/start-mode-routing.json` before selecting a startup/continuation mode.

- Bare `START`, `START RPi5_main`, `turpini`, or equivalent continuation means normal **FAST-LANE v2.2**. It is not `GITHUB-ONLY` and does not activate `AUTO-RUN FULL`.
- Activate `GITHUB-ONLY` only when the owner explicitly includes `GITHUB-ONLY` (or the documented `git hub only` spelling) in the current command.
- Activate `LIVE-ALL` only when the owner explicitly includes `LIVE-ALL` in the current command.
- Activate `AUTO-RUN FULL` only from the exact explicit form `AUTO-RUN FULL RPi5_main #<issue>` and then read `.github/auto-run-full-v1.json` plus `docs/AUTO_RUN_FULL_V1.md` before any activation write.
- Never infer an explicit mode from `.github/start-github-only.json`, deploy-queue state, handoff/issue continuity, executor availability, historical chat mode, controller state, or a prior authorization receipt.
- A deploy queue, handoff, executor limitation or authorization receipt may affect the selected lane after routing, but it must never rewrite the command mode itself.

<!-- BEGIN FAST-LANE-V2.2-MANAGED -->
## FAST-LANE v2.2 Composite

Read `docs/FAST_LANE_V2_2.md` as the active RPi5-specific startup contract.

**Primary rule:** the human approves the **RISK / DECISION**; automation executes the **TECHNICAL STEPS**.

- `START`, `turpini`, or equivalent continuation may carry Git/source/documentation/test work through Ready when it does not inspect protected runtime data and does not mutate host/runtime state.
- FAST may batch **2-5 closely related same-risk work items** and use up to **two scope-preserving corrective commits** for CI/review findings.
- Normal delivery has at most two owner gates: explicit **MERGE**, then one bounded **COMPOSITE LIVE** only when host/runtime mutation is required.
- CI polling, exact-SHA evidence, read-only preflight, checkout discovery, clean/ancestor validation, build preparation and reconciliation are technical automation steps, not owner gates.
- Composite Live must bind exact Git SHA, exact host/target, allowed mutation categories, hard limits where practical, explicit exclusions and expected baseline. It may include only explicitly named trusted `git fetch` + `git merge --ff-only`; it never implies reset/rebase/clean/force.
- Authorization is consumed at the first authorized mutation. Any later error, ambiguity or drift requires evidence preservation and STOP; no automatic retry, rollback, cleanup, reset, rebase or alternate mutation path unless explicitly pre-authorized.
- **STRICT is the default for host/runtime work**: sudo/root, packages, services/timers, Docker, networking/firewall/DNS/Cloudflare Tunnel, SSH/users/mounts/kernel, backups, databases/application data, secrets/credentials and protected runtime inspection.
- Put any remaining owner decision visibly at the end under `ACTION REQUIRED` and provide exact copyable input when needed.
- Merge remains explicit owner authority and never by itself authorizes host/runtime mutation. A valid `AUTO-RUN FULL RPi5_main #<issue>` activation is a separate explicit owner decision whose frozen issue envelope may include merge and predeclared runtime authority under the AUTO-RUN contract; it is never inferred from FAST continuation.

This FAST-LANE block does not weaken any earlier forbidden-path or production-safety rule. If classification is uncertain, classify STRICT and STOP.
<!-- END FAST-LANE-V2.2-MANAGED -->

<!-- BEGIN AUTO-RUN-FULL-V1-MANAGED -->
## AUTO-RUN FULL v1

Canonical local contract: `.github/auto-run-full-v1.json` and `docs/AUTO_RUN_FULL_V1.md`. Durable controller state: issue `#295`. Roadmap: issue `#294`.

- `AUTO-RUN FULL RPi5_main #<issue>` is one explicit, issue-specific owner decision. It is not blanket repository authority and is never inferred from `START`, `turpini`, prior chat context, issue continuity or controller state.
- Before activation, freshly read repository rules, the exact target issue, current `main`, active PR/CI/review state, relevant dependencies and controller issue `#295`.
- Materialize the frozen issue-specific authorization as an owner-identity GitHub activation receipt before using FULL authority. Later issue edits never silently expand that frozen authority.
- Inside the frozen envelope, routine analysis/source/docs/tests, branch/commit/PR work, CI/review/fix convergence and ordinary merge-conflict corrections require no additional owner nudge.
- The explicit AUTO-RUN FULL command is merge authority only for the canonical PR implementing that exact frozen issue. Merge requires a fresh exact head, required green CI, zero unresolved actionable review findings and no force/history rewrite.
- Runtime/live authority exists only for mutation classes and targets frozen at activation. Use existing reviewed operation registries, queue/baseline checks and the `#236` LIVE-AUTH protocol where applicable; do not create arbitrary SSH/sudo/shell authority.
- The agent itself still must not run `sudo`, obtain autonomous root, read protected secrets/configuration or bypass the earlier production safety boundary. AUTO-RUN may drive an already-reviewed narrow executor only through its declared GitHub authorization protocol.
- A ChatGPT turn/session ending is resumable state, not a STOP. Persist continuation in GitHub and allow the hourly Scheduled Task or a manual `turpini` resume trigger to continue from canonical state.
- If ChatGPT/app permissions require a product-level confirmation, persist `PAUSED_PLATFORM_APPROVAL`; repository policy cannot suppress a platform-mandated approval.
- Provider LLM API keys, token-billed fallback and automatic paid-credit purchase are forbidden by default.
- Three materially identical failed attempts without a new safe hypothesis produce `STOP_ERROR`; do not loop blindly.
- Normal terminal state is `DONE`. `STOP_SCOPE_OR_RISK` is only for genuinely new scope/mutation authority that was not frozen by the explicit AUTO-RUN activation.
<!-- END AUTO-RUN-FULL-V1-MANAGED -->

<!-- BEGIN GITHUB-ONLY-LIVE-ALL-V1-MANAGED -->
## GITHUB-ONLY / LIVE-ALL v1

Canonical shared contract: `rozkalnsandris/ops-workflows/docs/GITHUB_ONLY_LIVE_ALL.md` with machine invariants in `policy/github-only-live-all-v1.json`.

- `GITHUB-ONLY` (including `git hub only`) means fresh GitHub state, Git/source/documentation/test work, and preparation of a required rollout up to but not including the first host/runtime/live mutation.
- Persist deferred rollout state as public-safe `[DEPLOY-QUEUE]` issues in `rozkalnsandris/ops-workflows`; chat or memory is never the queue.
- Merge remains separately explicit. Neither `GITHUB-ONLY` nor `LIVE-ALL` authorizes merge.
- A GitHub write whose deterministic side effect changes production/runtime counts as live work and must not run under `GITHUB-ONLY`.
- Queue `READY` requires the final exact deployable SHA plus exact target alias, reviewed repository entrypoint, preflight, verification, allowed mutation categories/limits and no outstanding separate prerequisite owner gate.
- `LIVE-ALL` snapshots only open `READY` queue items present at command start, freshly revalidates each exact SHA/target/baseline and may execute only ordinary predeclared rollout mutations that this repository already permits inside the exact authorization envelope.
- sudo/root, packages, services/timers, Docker authority, networking/firewall/DNS/Tunnel, SSH/users/mounts/kernel, backups, databases/application data, secrets/credentials and protected runtime inspection remain STRICT/separately gated unless the exact repository-local contract explicitly includes that category.
- After any selected live mutation starts, error/ambiguity requires public-safe evidence preservation and STOP of the remaining batch; no automatic retry/rollback/cleanup/reset/rebase/alternate mutation path unless explicitly pre-authorized.
- All earlier production-safety and forbidden-data rules remain authoritative and stricter where applicable.
<!-- END GITHUB-ONLY-LIVE-ALL-V1-MANAGED -->

<!-- BEGIN START-GITHUB-ONLY-V1-MANAGED -->
## START_GITHUB_ONLY_V1 deterministic bootstrap amendment

Startup contract: `rozkalnsandris/ops-workflows/docs/START_GITHUB_ONLY_V1.md`.
Repository manifest: `.github/start-github-only.json`.

- `START <repository> GITHUB-ONLY` refreshes local rules/handoff, the pinned shared policy and START contract, current default branch/governance capability, active PRs, active issues/dependencies, and relevant deploy-queue items before selecting the manifest-defined canonical lane.
- Revalidate mutable GitHub state immediately before every state-dependent write.
- The absence of an open issue alone is NOT a STOP condition. Do not invent speculative work.
- If declared tie-breakers cannot resolve equally authoritative lanes, report `AMBIGUOUS_CANONICAL_LANE` instead of choosing arbitrarily.
- Final routing is one of `READY_FOR_MERGE`, `PARKED`, `STOP_ERROR`, `NEW_SCOPE_OR_RISK`, `AMBIGUOUS_CANONICAL_LANE`, or `IDLE`.
- `PARKED` is session-only. **EXECUTOR** availability is session capability, not **READY** rollout eligibility.
- Executor unavailability alone must not change `READY` to `BLOCKED`; use `BLOCKED` only for rollout eligibility or contract failure.
- Repository-local stricter safety and trust-boundary rules remain authoritative.
<!-- END START-GITHUB-ONLY-V1-MANAGED -->
