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
