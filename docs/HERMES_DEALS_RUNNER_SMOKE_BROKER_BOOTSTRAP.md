# Hermes Deals runner-smoke broker bootstrap

Issues: `RPi5_main#570`, checkout-isolation hardening `RPi5_main#576`, versioned v2 checkout `RPi5_main#584`, payload-closure repair/v3 continuation `RPi5_main#588`

This package is the source-side host-install bridge for the identity-only runner-smoke broker introduced by `#568/#569`. It does not grant LIVE authority and source merge does not install or activate anything.

## Fixed authority surface

The root-only source entrypoint is:

`ops/bin/rpi5-hermes-deals-runner-smoke-broker-bootstrap`

It accepts no arguments. The implementation fixes the dedicated trusted checkout identity, repository origin, detached-head requirement, release root, runtime dependency closure, systemd source/destination paths and socket unit. It does not accept caller-selected command, path, argv, environment, unit, UID/GID, SHA, operation or mutation sequence.

The current repair authority checkout is exclusively:

`RPi5_main-runner-smoke-broker-bootstrap-v3-trusted`

It must be clean, detached, at the reviewed `https://github.com/rozkalnsandris/RPi5_main.git` origin, and its `HEAD` must equal freshly fetched `origin/main` and the exact owner-authorized current main SHA.

The two earlier runner-smoke checkouts are immutable historical evidence only:

- `RPi5_main-runner-smoke-broker-bootstrap-trusted` (v1);
- `RPi5_main-runner-smoke-broker-bootstrap-v2-trusted` (v2).

Neither may be reset, switched, cleaned, removed, repaired or reused as v3 authority. The Weather-v12 checkout `RPi5_main-v12-engine-trusted` and every `RPi5_main-weather-*` checkout are also outside runner-smoke authority and cleanup scope.

The release root remains:

`/usr/local/libexec/rozkalns-runner-smoke-install`

A future authorized install publishes one SHA-addressed release below `releases/<RPi5_main SHA>` and makes `current` point only to that release. The systemd service continues to execute:

`/usr/local/libexec/rozkalns-runner-smoke-install/current/ops/bin/rpi5-hermes-deals-runner-smoke-install-broker`

The repaired runtime package is a fixed minimal closure. It contains the broker entrypoint, the explicit Python module dependency set, and exactly two non-import payload source artifacts required by the fixed installer:

- `ops/bin/hermes-deals-runner-smoke-audit`;
- `ops/deploy/hermes-deals-runner-smoke-audit-registration.json`.

The installer derives its source root from its installed module location inside the SHA release and validates these payloads against the fixed helper/registration SHA-256 identities before any destination write. The broker bootstrap therefore publishes immutable source bytes inside its own release but does not invoke the helper or install either payload into the final runner-smoke destinations. The exact-tree verifier rejects missing payloads, unreviewed extras and unexpected directories. There is no dynamic import discovery and no whole-repository copy.

## Issue #576 trusted source isolation

The v1 source-delivery contract is:

`ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-source-trusted-checkout-bootstrap.json`

It created `RPi5_main-runner-smoke-broker-bootstrap-trusted`. That checkout is historical evidence and has no current mutation authority.

## Issue #584 versioned v2 source authority

The v2 source-delivery contract is:

`ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-v2-source-trusted-checkout-bootstrap.json`

The matching v2 host-bootstrap contract is:

`ops/deploy/hermes-deals-runner-smoke-broker-bootstrap-v2.json`

V2 solved the previous stale-checkout problem by creating a new exact-main checkout rather than mutating v1. After subsequent main movement, that same rule makes v2 historical: a stale v2 path is `CONFLICT`, and its contract grants no reset/clean/remove/repair or alternate-path authority.

## Issue #588 v3 source authority and payload closure

The current source-delivery contract is:

`ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-v3-source-trusted-checkout-bootstrap.json`

The matching host-bootstrap contract is:

`ops/deploy/hermes-deals-runner-smoke-broker-bootstrap-v3.json`

V3 preserves both earlier checkouts and may create only `RPi5_main-runner-smoke-broker-bootstrap-v3-trusted`. The long-lived manager checkout may remain stale, dirty or detached; its working tree and index are not mutated. Under a separate exact owner LIVE authorization, v3 source delivery may perform at most one `git fetch origin main` in manager repository metadata and one detached `git worktree add` at the fixed v3 path. Before worktree creation, fresh `origin/main` must equal the exact authorized current main SHA and all required exact-main checks must be successful.

V3 source-delivery preflight has exactly three states:

- `ABSENT`: fixed v3 checkout path and worktree registration are absent;
- `EXACT_CLEAN`: fixed v3 checkout exists at the exact authorized SHA, detached, clean and at the reviewed origin;
- `CONFLICT`: any wrong v3 path, registration, origin, SHA, attached branch or dirty state.

`CONFLICT` fails closed. There is no reset, rebase, clean, stash, checkout/switch, worktree remove/prune/repair, alternate checkout, retry, cleanup or rollback authority. V1/v2 and Weather checkouts remain explicit preserve-only namespaces.

Source delivery does not authorize the host bootstrap. The host bootstrap is a second separate owner LIVE gate after sanitized v3 checkout verification.

## #31 partial install evidence and root cause

LIVE-AUTH `rozkalnsandris/deploy-authorizations#31` reached the fixed capability-install mutation boundary and created the dedicated `hermes-deals-audit-canary` group/user. It then failed closed at `safe_stage=install_execution` before the helper destination parent existed. Read-only poststate showed:

- group/user present with the dedicated primary group, `/nonexistent` home and `/usr/sbin/nologin` shell;
- helper destination `ABSENT`;
- registration destination `ABSENT`;
- `/usr/local/libexec/rozkalns-deploy` `ABSENT`;
- `/etc/rozkalns-deploy` `ABSENT`.

The installed `db6deecf…` broker release omitted the two non-import payload source artifacts consumed by `PosixFixedInstallBackend._source_artifact()`. Therefore the source lookup failed after identity creation and before `_install_bytes()` could create either destination parent. LIVE-AUTH #31 is permanently non-reusable; this source repair does not retry, clean up or roll back that partial state.

## Exact predecessor broker upgrade

The active predecessor broker release is fixed to:

`db6deecffbc3a46a475d1fd9db97fc679eb15cf8`

That SHA-addressed release is never rewritten or deleted. V3 recognizes it as `LEGACY_EXACT` only when all of the following hold simultaneously:

- release root and releases root are exact root-owned/mode-fixed directories;
- the releases set contains only `db6deecf…`;
- `current` points exactly to that release;
- historical runtime closure bytes, paths, modes and ownership are exact;
- fixed systemd unit bytes are exact;
- socket state is `enabled/active`.

Any extra/missing file, alternate SHA, unit drift, socket drift, `current.next`, partial prior upgrade or other mixed state is `DRIFT` and fails closed.

A later separately authorized `LEGACY_EXACT` upgrade has only two mutation classes:

1. publish one new root-owned SHA release containing the repaired fixed closure;
2. create fixed `current.next` and atomically replace `current` with it.

The predecessor release remains present as immutable evidence. Existing systemd unit files are not rewritten; `daemon-reload`, restart and re-enable are not part of the upgrade. Python `os.replace()` is used for the same-filesystem symlink switch; on POSIX a successful replacement is atomic. There is no automatic retry, cleanup, rollback or predecessor deletion. Any error after the first mutation is STOP and requires a new explicit recovery decision after minimum read-only evidence.

## Host bootstrap state machine

Only these pre-mutation states are accepted by v3:

- `ABSENT`: capability-owned broker release/unit paths are absent and the fixed socket is not active/enabled. Plan: `INSTALL_REQUIRED_EXPLICIT_LIVE`.
- `LEGACY_EXACT`: exact `db6deecf…` predecessor release, exact unit bytes and active/enabled socket. Plan: `UPGRADE_REQUIRED_EXPLICIT_LIVE`.
- `EXACT`: current source release is exact. It may be the sole release after a fresh install, or coexist only with preserved exact `db6deecf…` after the bounded upgrade. Result: `ALREADY_EXACT_NO_MUTATION`.

Any mixed, partial, stale or conflicting host state fails closed before the first new mutation.

A fresh install from `ABSENT` remains limited to:

1. publish the root-owned SHA release;
2. publish the fixed `current` symlink;
3. publish the two fixed systemd unit files;
4. run `systemctl daemon-reload`;
5. run `systemctl enable --now rozkalns-hermes-deals-runner-smoke-install.socket`.

The `LEGACY_EXACT` upgrade instead uses only the two-step release-publication/current-switch sequence above.

## Required owner-gate order

1. merge the reviewed #588 repair and require fresh exact-main CI;
2. create/revalidate the exact current v3 trusted checkout under its own separately authorized source-delivery gate if required;
3. verify broker host state read-only;
4. if it is exact `db6deecf…`, separately authorize only the bounded `LEGACY_EXACT` broker upgrade and verify `current` points to the repaired exact release while the predecessor remains preserved;
5. re-evaluate the partial runner-smoke capability-install poststate and prepare a new separately owner-authorized recovery envelope that treats the existing exact group/user as pre-existing state; never reuse #31;
6. only after exact capability-install verification may a later genuine runner-smoke canary be considered under its own gate.

## Explicit exclusions

This source merge does not authorize v3 source delivery, broker upgrade or capability-install recovery. The bootstrap does not invoke the runner-smoke helper, install helper/registration payloads into `/usr/local/libexec/rozkalns-deploy` or `/etc/rozkalns-deploy`, create or consume LIVE-AUTH/replay state, mutate the runner-smoke execution identity, delete/rewrite the `db6deecf…` predecessor release, change RDC `NoNewPrivileges`, mutate Docker/network/firewall/DNS/Cloudflare/DB/credentials/secrets/runner settings, mutate or clean manager/v1/v2/Weather worktrees, or deploy production.

Before any host execution, a separate explicit LIVE authorization must bind the exact reviewed `RPi5_main` SHA, exact current CI, v3 trusted checkout state, expected host baseline, exact mutation envelope, verification and failure semantics.
