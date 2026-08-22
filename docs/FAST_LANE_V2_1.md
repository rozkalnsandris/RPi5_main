# FAST-LANE v2.2 Composite — RPi5_main

> Compatibility path: `AGENTS.md` already points to this v2.1 filename; these are the authoritative v2.2 rules.

## Core rule

**The human approves the RISK / DECISION. Automation executes the TECHNICAL STEPS.** Read-only checks never create owner gates. STRICT describes host/runtime mutation risk, not approval-per-command.

## FAST

Git-only documentation, source, tests and policy/orchestration code may proceed from fresh canonical GitHub state through Ready in one coherent batch when they do not read protected runtime data or mutate the host. This includes branch, PR, CI/review and up to two scope-preserving corrections. Batch 2-5 closely related same-risk items when coherent. Merge remains explicit.

## Human gate budget

Normal delivery has at most two owner gates: **MERGE**, then **COMPOSITE LIVE** only when host/runtime mutation is required. CI polling, exact-SHA evidence, read-only preflight, checkout discovery, clean/ancestor validation, build preparation and reconciliation are automation steps.

## Composite STRICT

One live authorization may cover tightly coupled operations required for one bounded host/runtime action when it binds exact Git SHA, exact host/target, allowed mutation categories, hard limits, explicit exclusions and expected baseline. A trusted local checkout may perform only explicitly allowed `git fetch` + `git merge --ff-only` inside the same envelope when needed; this never implies `reset`, `rebase`, `clean` or force operations.

Preflight is the beginning of the same fail-closed one-shot. Revalidate SHA/host/baseline immediately before first mutation and stop on drift. Use pinned tooling and exact artifacts where applicable.

## Local STRICT boundaries

Sudo/root, packages, services/timers, Docker, networking/firewall/DNS/Cloudflare Tunnel, SSH/users/mounts/kernel, backups, databases/application data, secrets/credentials, protected configuration/runtime inspection or another host/runtime mutation require Composite Live authorization. Uncertain live classification is STRICT.

## Failure and evidence

Authorization is consumed at the first authorized mutation. Any later error/ambiguity requires evidence preservation and STOP; no automatic retry, rollback, cleanup, reset, rebase or alternate mutation path unless explicitly pre-authorized.

Use one Ready receipt and one final live receipt. Put any remaining owner decision at the **end** under `ACTION REQUIRED`; when the owner must enter/run something, provide the exact copyable instruction in a fenced `bash` block.

Merge never authorizes host/runtime mutation.
