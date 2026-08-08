# V20 Hermes Tech ephemeral release-control bootstrap

## Status

Source/CI only. Merging this bootstrap performs no host mutation.

Issue #81 exists because the normal operator working checkout became unusable for source synchronization after its Git index ownership drifted. Production recovery must not depend on repairing or mutating that day-to-day checkout.

## Design

`ops/bin/hermes-tech-http-policy-v20-release-control` is a narrow owner bootstrap for the already reviewed V20 recovery operator merged by PR #79.

Every invocation requires an exact 40-hex `--expected-sha` and one explicit mode:

- `check` — delegates only to the recovery operator's read-only preflight;
- `apply` — separately requested recovery cutover under the recovery operator's rollback contract;
- `verify` — read-only post-recovery verification.

The bootstrap:

1. resolves public `origin/main` and requires exact equality with the approved SHA;
2. requires one successful GitHub-hosted `Validate` push run for that exact `main` SHA and exactly one successful `validate` job;
3. creates a fresh temporary single-branch `main` clone;
4. requires clean `main`, `HEAD == origin/main == expected SHA` inside that clone;
5. requires the reviewed PR #79 merge to be an ancestor;
6. pins the PR #79 recovery operator by its Git blob identity so unrelated later `main` commits may advance without silently changing the production recovery program;
7. delegates the requested mode to that reviewed recovery operator;
8. removes the temporary release-control clone on exit.

## Ownership boundary

The bootstrap deliberately does not repair the normal checkout. It contains no recursive ownership change and does not run Git as root against a pre-existing operator checkout. The only Git repository it mutates is the fresh ephemeral clone that it created itself.

This follows Git's separation of per-worktree administrative state such as `HEAD` and `index`: production source selection should use dedicated release-control state instead of depending on a mutable development checkout.

## Public repository boundary

No RPi5 self-hosted GitHub Actions runner is added. GitHub-hosted `Validate` remains the source CI authority; the later owner invocation occurs directly on the host outside GitHub Actions.

The bootstrap does not use repository/environment secrets, an authorization header, `GITHUB_TOKEN`, or `GH_TOKEN`. It queries only public GitHub repository metadata and validation status.

## Mutation boundary

The bootstrap itself does not contain systemd, Docker, firewall, Cloudflare, database, content-generation, image lifecycle, reboot, Git history rewrite, or normal-checkout mutation logic. Runtime authority remains entirely in the separately reviewed recovery operator.

A merge authorizes no host execution. Production still requires an explicit owner invocation, beginning with `check`.
