---
name: rpi5-main
description: Use for repository-specific work in rozkalnsandris/RPi5_main: source/governance changes, RPi5 deployment preparation, exact-SHA evidence, AUTO-RUN FULL routing, CI/review convergence, and bounded LIVE-gate preparation. This skill never grants sudo/root, protected-runtime inspection, merge, or host/LIVE authority.
---

# RPi5_main workflow

Follow repository `AGENTS.md` first. This skill is guidance only and must never weaken, replace, or silently expand repository authority.

## 1. Resolve authority before work

1. Read `AGENTS.md` and `.github/start-mode-routing.json`.
2. Identify the exact current user command and the one current work item/lane.
3. Refresh current `main` and only the issue/PR/CI/review/controller/deploy-queue state required for that lane.
4. Do not infer `GITHUB-ONLY`, `LIVE-ALL`, or `AUTO-RUN FULL` from chat history, issue names, controller state, deploy queues, executor availability, or old authorization receipts.
5. For explicit `AUTO-RUN FULL RPi5_main #<issue>`, read `.github/auto-run-full-v2.json`, `docs/AUTO_RUN_FULL_V2.md`, the exact issue/DoD, controller issue, and current relevant PR/CI/review/dependency state before activation work.
6. Treat GitHub as canonical for mutable source, issue, PR, review, check, SHA, and continuation state.

This skill itself never grants merge, LIVE, sudo/root, runtime inspection, retry, rollback, cleanup, credential, permission, package, service, Docker, network, database, or filesystem mutation authority.

## 2. Preserve the production safety boundary

Never autonomously:

- run `sudo` or obtain root;
- install/remove/upgrade packages;
- restart/reload/stop/enable/disable services or timers;
- mutate Docker, networking, firewall, DNS, Cloudflare Tunnel, SSH, users, mounts, kernel, backups, databases, application data, permissions, or ownership;
- read process/container environments, use `docker inspect`, or copy protected configuration trees;
- read, print, copy, log, or commit `.env`, secrets, credentials, tokens, cookies, password stores, SSH keys, database data/dumps, backups, browser/session data, shell history, Docker volume/runtime data, Home Assistant `.storage`, or other forbidden paths/data named by `AGENTS.md`.

If classification is uncertain, classify the operation STRICT and stop at the correct owner gate.

## 3. Keep source work minimal and reviewable

1. State the verified problem or acceptance target in one sentence.
2. Read the smallest set of source, tests, policies, and docs that own the behavior.
3. Make the smallest coherent change; preserve unrelated automation and trust boundaries.
4. Stage exact paths only; never use `git add .`, `git add -A`, or `git add --all`.
5. Run the narrowest applicable checks first, then broader checks required by the touched boundary.
6. Inspect the final diff for accidental files, generated evidence, secrets, unsafe live capability, and authority expansion.
7. Use a focused branch and Draft PR; never force-push or rewrite history.

Do not commit generated runtime evidence unless the repository explicitly authorizes a sanitized fixture for the task.

## 4. Separate source readiness from runtime truth

Always distinguish:

- source implementation/readiness;
- exact-head CI/review readiness;
- merge readiness;
- deploy/live eligibility;
- actual production verification.

Do not claim production success from source inspection, tests, CI, or a prepared deploy contract alone.

Read-only exact-SHA validation, checkout discovery, ancestor/clean checks, build preparation, reconciliation, and evidence refresh are technical steps when the active contract permits them; they must not be turned into artificial owner gates.

## 5. Respect the active execution lane

- FAST is the safe discovery/audit/non-FULL lane and may carry allowed Git/source/docs/tests work through Draft PR, CI/review convergence, and Ready.
- FAST merge remains explicit owner authority.
- FULL exists only after exact issue-scoped activation and a valid frozen authorization receipt.
- FULL merge authority applies only to the exact canonical issue/PR envelope and never implies unrestricted host/runtime mutation.
- Runtime/live actions may use only the exact reviewed executor/registry/queue/authorization mechanism allowed by the current repository contract; never invent arbitrary SSH/sudo/shell authority.
- `GITHUB-ONLY` stops before the first live/runtime mutation.
- `LIVE-ALL` covers only the predeclared READY queue items and mutation classes validly included by the current contract.

After the first authorized live mutation begins, any error, timeout, drift, or ambiguous result means preserve public-safe/read-only evidence and STOP unless the exact retry/rollback/cleanup/recovery path was pre-authorized.

## 6. Use current documentation for changing platform semantics

When work depends on current GitHub, Cloudflare, Docker, systemd, Debian/Raspberry Pi, ChatGPT/Codex, or other external platform behavior, verify current authoritative documentation before implementing or changing contracts. Repository-local stricter safety rules remain authoritative even when external docs permit more.

## 7. Report in the repository's required terminal form

Return concise evidence:

- problem/root cause or acceptance target;
- exact files changed;
- tests/checks and exact results;
- source versus runtime evidence boundary;
- security/deploy/LIVE impact;
- remaining uncertainty/blocker.

Finish with exactly one owner command under `NEXT COMMAND` or `ACTION REQUIRED` as required by current `AGENTS.md`. Do not offer a menu of alternative commands.
