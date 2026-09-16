# Hermes Deals runner-smoke broker bootstrap

Issue: `RPi5_main#570`

This package is the source-side host-install bridge for the identity-only runner-smoke broker introduced by `#568/#569`. It does not grant LIVE authority and source merge does not install or activate anything.

## Fixed authority surface

The root-only source entrypoint is:

`ops/bin/rpi5-hermes-deals-runner-smoke-broker-bootstrap`

It accepts no arguments. The implementation fixes the trusted checkout identity, repository origin, branch, release root, runtime dependency closure, systemd source/destination paths and socket unit. It does not accept caller-selected command, path, argv, environment, unit, UID/GID, SHA, operation or mutation sequence.

The release root is:

`/usr/local/libexec/rozkalns-runner-smoke-install`

A future authorized install publishes one SHA-addressed release below `releases/<RPi5_main SHA>` and makes `current` point only to that release. The service continues to execute:

`/usr/local/libexec/rozkalns-runner-smoke-install/current/ops/bin/rpi5-hermes-deals-runner-smoke-install-broker`

The runtime package is a fixed minimal module closure. The installer does not dynamically discover imports and does not copy the whole repository.

## State machine

Only two pre-mutation states are accepted:

- `ABSENT`: capability-owned release/unit paths are absent and the fixed socket is not active/enabled. The plan is `INSTALL_REQUIRED_EXPLICIT_LIVE`.
- `EXACT`: the source bytes, owner/modes, SHA release, `current` link, two systemd unit files, enabled state and active socket all match. The result is `ALREADY_EXACT_NO_MUTATION`.

Any mixed, partial, stale or conflicting state fails closed before the first new mutation.

The future fixed mutation sequence is limited to:

1. publish the root-owned SHA release;
2. publish the fixed `current` symlink;
3. publish the two fixed systemd unit files;
4. run `systemctl daemon-reload`;
5. run `systemctl enable --now rozkalns-hermes-deals-runner-smoke-install.socket`.

After the first future mutation, any error is terminal for that authorization context. There is no automatic retry, cleanup, rollback, alternate release or alternate systemd action.

## Explicit exclusions

This bootstrap does not invoke the runner-smoke helper, create or consume LIVE-AUTH/replay state, mutate the runner-smoke payload identity/helper/registration, change RDC `NoNewPrivileges`, mutate Docker/network/firewall/DNS/Cloudflare/DB/credentials/secrets/runner settings, or deploy production.

Before any host execution, a separate explicit LIVE authorization must bind the exact reviewed `RPi5_main` SHA, exact current CI, trusted checkout state, expected host baseline, exact mutation envelope, verification and recovery semantics.
