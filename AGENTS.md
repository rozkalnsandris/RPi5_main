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
- Merge remains explicit owner authority and never authorizes any host/runtime mutation.

This FAST-LANE block does not weaken any earlier forbidden-path or production-safety rule. If classification is uncertain, classify STRICT and STOP.
<!-- END FAST-LANE-V2.2-MANAGED -->
