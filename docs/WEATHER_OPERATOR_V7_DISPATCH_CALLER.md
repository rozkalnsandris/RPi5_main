# Weather v7 identity-only dispatch caller

Status: SOURCE-ONLY / CALLER HOST INSTALL REQUIRED  
Issue: `RPi5_main#591`  
Operation: `rpi5-main.weather-operator-upgrade-v7.v1`

## Purpose

`RPi5_main#591` closes the gap between the reviewed root Weather-v7 broker socket and the unprivileged control plane without changing the socket ACL, adding the owner to `rozkalns-deploy-executor`, granting `sudo`, enabling P8 mutation dispatch or introducing a generic privileged executor.

The caller is operation-specific. It runs as the existing `rozkalns-deploy-executor` service identity, receives the existing GitHub App credential only through `systemd LoadCredential`, polls only `rozkalnsandris/ops-workflows` for the exact open title `[LIVE-AUTH][PENDING] rpi5-main-weather-operator-upgrade-v7`, and can submit only the existing `rozkalns.deploy-dispatch-request.v1` identity tuple to `/run/rozkalns-weather-operator-v7-capability/request.sock`.

No command, path, argv, environment, source SHA, target, mutation budget, rollback instruction or executable selection crosses the socket boundary. The root broker remains the only mutation-capable component and independently re-fetches and revalidates owner identity, TTL, UUID, queue binding, current `RPi5_main` main, exact-SHA CI, installed capability registration, baseline, predecessor hash, v6 preservation and durable replay state before any fixed 1+1+1 operator-upgrade mutation begins.

## No automatic retry

The caller persists the exact request UUID to its dedicated `0700` systemd `StateDirectory` **before** opening the broker socket. Once a UUID reaches that attempt boundary, the timer never submits it again, whether the socket connect, broker validation or privileged operation succeeds or fails. Recovery requires a new owner-authored LIVE authorization with a new UUID.

This caller-side ledger is defense in depth. The root broker keeps its independent replay database and consumes the authorization before entering its mutation sequence.

## Required gate order

Source merge does not install or activate the caller.

1. Merge the `RPi5_main#591` source outcome and require exact-main CI.
2. Under a separate exact owner LIVE authorization, create immutable detached checkout `RPi5_main-weather-v7-dispatch-caller-installer-source-trusted` using only one reviewed `git fetch origin main` and one fixed detached `git worktree add`.
3. Verify exact SHA, detached-clean state, reviewed origin and required caller installer paths.
4. Under another separate exact owner LIVE authorization, run `scripts/install-weather-operator-v7-dispatch-caller.py --apply`.
5. Verify the four new caller artifacts, `rozkalns-deploy-executor` service identity, enabled timer and unchanged broker socket ownership/mode without reading credentials.
6. Create a **new** owner-authored Weather-v7 LIVE authorization and UUID; historical/expired identities remain non-reusable.
7. Let the operation-specific caller submit that identity once to the fixed broker and verify the installed operator closure.
8. Return to `rozkalns_weather#136` Phase B queue/JIT reconciliation before Weather application rollout.

The source-delivery gate does not authorize installer apply. The caller-install gate does not authorize the operator upgrade. The later operator authorization does not authorize Weather application deployment, Docker/systemd application mutation, database/corpus writes, Cloudflare/network changes or secrets/credential mutation.

## Installation boundary

Machine contracts:

- `ops/deploy/rpi5-main-weather-v7-dispatch-caller-installer-source-trusted-checkout-bootstrap.json`
- `ops/deploy/weather-public-runtime-operator-upgrade-v7-dispatch-caller-installer.json`

The installer is first-install-only. It requires the existing Weather-v7 broker socket enabled+active and requires the installed broker/dispatch modules/socket/service bytes to match the exact reviewed source. It adds only the operation-specific caller module, fixed caller executable, one fixed `oneshot` service and one fixed timer.

The service runs as `User=rozkalns-deploy-executor` and `Group=rozkalns-deploy-executor`, with `NoNewPrivileges=true`, a private state directory, fixed `LoadCredential`, and no writable path except its state directory. Installation does not replace the broker, change socket permissions/ACLs, change users/groups, replace the Weather operator, create the v7 operator checkout, enable P8/global mutation dispatch, deploy Weather, or touch database/corpus/network/Cloudflare state.

## Fail-closed semantics

Every LIVE gate consumes its authorization at its first authorized mutation. After mutation starts, error, source/head/CI drift, checkout conflict, installer failure or verification mismatch permits only minimum sanitized read-only evidence and STOP. No automatic retry, cleanup, rollback, reset, rebase, worktree repair, permission workaround or alternate privileged transport is implied.
