# Hermes Deals runner-smoke broker bootstrap

Issues: `RPi5_main#570`, checkout-isolation hardening `RPi5_main#576`, versioned checkout continuation `RPi5_main#584`, payload-closure repair `RPi5_main#588`

This package is the source-side host-install bridge for the identity-only runner-smoke broker introduced by `#568/#569`. It does not grant LIVE authority and source merge does not install or activate anything.

## Fixed authority surface

The root-only source entrypoint is:

`ops/bin/rpi5-hermes-deals-runner-smoke-broker-bootstrap`

It accepts no arguments. The implementation fixes the dedicated trusted checkout identity, repository origin, detached-head requirement, release root, runtime dependency closure, systemd source/destination paths and socket unit. It does not accept caller-selected command, path, argv, environment, unit, UID/GID, SHA, operation or mutation sequence.

The current runner-smoke bootstrap authority checkout is exclusively:

`RPi5_main-runner-smoke-broker-bootstrap-v2-trusted`

It must be clean, detached, at the reviewed `https://github.com/rozkalnsandris/RPi5_main.git` origin, and its `HEAD` must equal the locally fetched `origin/main`.

The historical v1 checkout:

`RPi5_main-runner-smoke-broker-bootstrap-trusted`

is immutable evidence only. It is not current bootstrap authority and must not be reset, switched, cleaned, removed, repaired or reused for v2 source delivery. The former Weather-v12 checkout `RPi5_main-v12-engine-trusted` and every `RPi5_main-weather-*` checkout are also explicitly outside runner-smoke authority and cleanup scope.

The release root remains:

`/usr/local/libexec/rozkalns-runner-smoke-install`

A future authorized install publishes one SHA-addressed release below `releases/<RPi5_main SHA>` and makes `current` point only to that release. The service continues to execute:

`/usr/local/libexec/rozkalns-runner-smoke-install/current/ops/bin/rpi5-hermes-deals-runner-smoke-install-broker`

The runtime package is a fixed minimal closure. It contains the broker entrypoint, the explicit Python module dependency set, and exactly two non-import payload source artifacts required by the fixed installer:

- `ops/bin/hermes-deals-runner-smoke-audit`;
- `ops/deploy/hermes-deals-runner-smoke-audit-registration.json`.

The installer resolves its source root from its installed module location inside the SHA release and validates these two payloads against the already-fixed helper/registration SHA-256 identities before any destination write. The bootstrap therefore publishes the immutable source bytes inside its own release but does not invoke the helper or install either payload into the final runner-smoke destinations. The exact-tree verifier rejects missing payloads, unreviewed extras and unexpected directories. There is no dynamic import discovery and no whole-repository copy.

## Issue #576 trusted source isolation

The historical v1 machine source-delivery contract is:

`ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-source-trusted-checkout-bootstrap.json`

That contract created `RPi5_main-runner-smoke-broker-bootstrap-trusted`. After `#580/#583` advanced `main`, the v1 checkout intentionally became historical evidence rather than being mutated in place.

## Issue #584 versioned v2 source authority

The current machine source-delivery contract is:

`ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-v2-source-trusted-checkout-bootstrap.json`

The matching host-bootstrap contract is:

`ops/deploy/hermes-deals-runner-smoke-broker-bootstrap-v2.json`

The long-lived manager checkout may remain stale, dirty or detached and its working tree is not mutated. A later separate source-delivery LIVE authorization may permit at most one `git fetch origin main` in manager repository metadata and one detached `git worktree add` at the fixed v2 path and exact owner-authorized current `RPi5_main/main` SHA. Before worktree creation, fresh `origin/main` must equal that SHA and all five exact-main GitHub checks must be successful.

V2 source-delivery preflight has exactly three states:

- `ABSENT`: the fixed v2 checkout path and worktree registration are absent;
- `EXACT_CLEAN`: the fixed v2 checkout exists at the exact authorized SHA, detached, clean and at the reviewed origin;
- `CONFLICT`: any wrong v2 path, registration, origin, SHA, attached branch or dirty state.

`CONFLICT` fails closed. There is no reset, rebase, clean, stash, checkout/switch, worktree remove/prune/repair, alternate checkout, retry, cleanup or rollback authority. The v1 checkout is explicitly preserved with `mutation_allowed=false`, `cleanup_allowed=false` and `authority_source=false`.

Source delivery does not authorize the host bootstrap to run. The host bootstrap remains a second separate owner LIVE gate after sanitized v2 checkout verification.

## Host bootstrap state machine

Only two host pre-mutation states are accepted:

- `ABSENT`: capability-owned release/unit paths are absent and the fixed socket is not active/enabled. The plan is `INSTALL_REQUIRED_EXPLICIT_LIVE`.
- `EXACT`: the source bytes, owner/modes, SHA release, `current` link, two systemd unit files, enabled state and active socket all match. The result is `ALREADY_EXACT_NO_MUTATION`.

Any mixed, partial, stale or conflicting host state fails closed before the first new mutation.

The future fixed host mutation sequence remains limited to:

1. publish the root-owned SHA release;
2. publish the fixed `current` symlink;
3. publish the two fixed systemd unit files;
4. run `systemctl daemon-reload`;
5. run `systemctl enable --now rozkalns-hermes-deals-runner-smoke-install.socket`.

After the first future mutation, any error is terminal for that authorization context. There is no automatic retry, cleanup, rollback, alternate release or alternate systemd action.

## Required owner-gate order

1. merge the reviewed v2 source and require exact-main CI;
2. if the fixed v2 checkout is `ABSENT`, separately authorize exact-main v2 source delivery;
3. verify the v2 checkout is detached, clean, at the exact SHA and reviewed origin while v1 remains untouched;
4. separately authorize the runner-smoke broker host bootstrap if host state is still `ABSENT`;
5. verify the exact release, unit bytes, ownership/modes and active/enabled fixed socket;
6. only then continue to later runner-smoke canary/runtime-evidence gates under the parent Phase 4 plan.

## Explicit exclusions

This bootstrap does not invoke the runner-smoke helper, install helper/registration payloads into `/usr/local/libexec/rozkalns-deploy` or `/etc/rozkalns-deploy`, create or consume LIVE-AUTH/replay state, mutate the runner-smoke execution identity, change RDC `NoNewPrivileges`, mutate Docker/network/firewall/DNS/Cloudflare/DB/credentials/secrets/runner settings, mutate or clean manager/v1/Weather worktrees, or deploy production.

Before any host execution, a separate explicit LIVE authorization must bind the exact reviewed `RPi5_main` SHA, exact current CI, v2 trusted checkout state, expected host baseline, exact mutation envelope, verification and recovery semantics.