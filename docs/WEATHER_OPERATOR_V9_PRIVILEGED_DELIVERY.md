# Weather v9 privileged delivery successor

Status: **SOURCE-ONLY / HOST CAPABILITY + CALLER INSTALL REQUIRED**  
Issue: `RPi5_main#603`  
Operation: `rpi5-main.weather-operator-upgrade-v9.v1`

## Purpose

Issue #603 adds a new capability-specific privileged boundary for the Weather operator v9 compatibility upgrade merged by #601/#602. It does not reinterpret or mutate the Weather-v7 broker/caller. The v9 operation has its own authorization title/schema, Unix socket, replay database, registration, broker, identity-only caller and installer contracts.

The fixed runtime transition remains exactly the merged v9 transition:

- target: `/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_operator.py`;
- predecessor SHA-256: `48c8c5fb0cdc005bf0e4fbb05a203297e05d7ef62689ddd0d6d717c13acc0fcb`;
- target SHA-256: `d153db5707b1e37e8a3268fc80e57e75ae7248c5ea9f7ab169357b77849ed1a3`;
- checkout: `RPi5_main-weather-public-runtime-operator-upgrade-v9-trusted`;
- mutation budget: one fixed checkout fetch, one fixed detached worktree add and one atomic module replacement;
- rollback policy: `NONE`.

The root broker does not implement a second replacement algorithm. After owner-auth/READY/current-main/CI/predecessor/checkout/replay revalidation, it creates only the reviewed v9 checkout when absent and invokes the already-merged zero-argument `ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v9`. That entrypoint and module retain the #601 double-preflight, whole installed-closure validation and same-directory atomic replacement semantics.

## Identity-only trust boundary

The unprivileged caller runs as `rozkalns-deploy-executor` and polls only the exact v9 LIVE-AUTH title. It sends only the fixed `rozkalns.deploy-dispatch-request.v1` identity tuple over `/run/rozkalns-weather-operator-v9-capability/request.sock`.

No command, executable, path, argv, environment, source SHA, target, mutation budget or rollback instruction crosses the socket boundary. The broker independently re-fetches and validates the authorization issue and READY queue, requires exact current `RPi5_main` plus successful exact-SHA CI, verifies the installed predecessor and capability registration, preserves v8 historical evidence, and consumes durable replay state before the first authorized mutation sequence.

A v7 authorization is not v9 authority. The v7 operation/title/schema/socket/checkouts remain separate and are not accepted by the v9 caller or broker.

## Installation boundary

Source merge installs nothing.

Machine contracts:

- `ops/deploy/weather-public-runtime-operator-upgrade-v9-privileged-delivery.json`;
- `ops/deploy/rpi5-main-weather-v9-privileged-delivery-installer-source-trusted-checkout-bootstrap.json`;
- `ops/deploy/weather-public-runtime-operator-upgrade-v9-host-capability-installer.json`;
- `ops/deploy/weather-public-runtime-operator-upgrade-v9-dispatch-caller-installer.json`.

The future source-delivery gate may create only one exact detached installer checkout after one bounded `git fetch origin main`. The capability installer is first-install-only and creates the independent v9 support root, root broker/socket, private replay state and registration. The caller installer is separately first-install-only, verifies the exact capability source registration and prerequisites, then adds only the operation-specific caller/service/timer.

Both installers default to read-only preflight. Their `--apply` modes require a separate exact owner LIVE authorization and a root process; the conversational agent is never granted `sudo` or generic root.

## One-shot failure semantics

The caller writes its request UUID to a private attempt ledger before opening the broker socket and never retries the same UUID. The root broker has an independent replay database and consumes the authorization before checkout or replacement mutation.

After any authorized mutation starts, error, timeout, source/head/CI/authorization/queue drift, worktree conflict, predecessor mismatch, replacement failure or postcondition failure requires minimum sanitized read-only evidence and STOP. There is no automatic retry, cleanup, rollback, backup restore, checkout repair, alternate checkout or alternate privileged transport.

## Recovery after the v9 worktree mode failure

`RPi5_main#605` records the source-only recovery after owner LIVE authorization `ops-workflows#70` was consumed and the first v9 worktree was materialized under the broker service `UMask=0077`. Git preserved the reviewed executable bit semantically, but the inherited restrictive umask produced filesystem mode `0700`; the broker then rejected the fixed v9 entrypoint because its contract requires exact mode `0755`.

The recovery preserves the service-level `UMask=0077` and scopes `umask=0022` only to the manager-identity child process that performs the single authorized `git worktree add`. The broker process umask is not changed, fetch behavior is unchanged, and the mutation budget remains one fetch + one detached worktree add + one atomic replacement.

Authorization `ops-workflows#70` is spent and non-reusable. The partial v9 checkout, preserved v8 checkout and installed predecessor remain evidence; source recovery does not authorize retry, cleanup, rollback, `chmod`, worktree removal/repair or any LIVE/systemd/runtime mutation.

## Required later gate order

1. Merge #603 and require exact-main CI.
2. Separate owner LIVE: materialize `RPi5_main-weather-v9-privileged-delivery-installer-source-trusted` at the exact then-current `RPi5_main/main`.
3. Separate bounded owner LIVE: install the v9 host capability and identity-only caller from that exact trusted checkout (these tightly coupled first-install steps may share one explicitly frozen Composite LIVE envelope).
4. Verify installed hashes/ownership/modes, socket/timer state and absence of v7 mutation.
5. Create a fresh owner-authored v9 LIVE-AUTH and READY queue binding; no historical authorization is reusable.
6. Let the v9 caller dispatch once; verify the installed operator module is exactly `d153db57…`.
7. Only then perform fresh Weather public-runtime incident recovery / rollout reconciliation.

After #605 recovery is merged, the pre-recovery queue binding is stale. Any resumed v9 execution must bind a freshly reviewed source SHA and use a fresh owner LIVE authorization; neither `ops-workflows#69` nor spent authorization `ops-workflows#70` is sufficient authority for a new mutation.

## Post-#605 capability refresh gate

Issue #607 adds the source-only repair needed because the live v9 capability had already been first-installed from pre-recovery source `68ef2b73dc8600dd63cf2a3b6920814e27313600`. The first-install installer remains intentionally unchanged and continues to reject existing targets. It is not repurposed as an upgrade mechanism.

The reviewed #607 mechanism is a narrow in-place capability refresh described by `ops/deploy/weather-operator-v9-capability-refresh.json` and implemented by `scripts/refresh-weather-operator-v9-host-capability.py`. Its default mode is read-only preflight. A later `--apply` requires a separate owner LIVE authorization and root process.

The refresh admits only the exact pre-#605 installed state: registration must still bind the predecessor source; installed module, broker, socket and service hashes must exactly match that predecessor source; the durable replay/state database must remain present with fixed root-owned metadata; and both fixed staging paths must be absent. Target source must still keep the host-capability module, socket and rendered service byte-identical to the predecessor. Only the broker is allowed to differ.

The fixed mutation budget is two same-directory staging writes followed by two atomic replacements: broker first, registration second. No `systemctl` action is part of the refresh. The replay/state database contents are never read by the refresh operator and its metadata snapshot must be unchanged after the operation. If execution stops after broker replacement but before registration replacement, the old registration hash no longer matches the new broker and the capability therefore remains fail-closed rather than accepting a mixed identity. No automatic retry, cleanup or rollback is authorized.

After #607 source merge, the canonical gate order superseding the pre-recovery queue step is:

1. require exact merged `RPi5_main/main` and exact-main CI;
2. collect fresh bounded read-only live evidence that the installed capability exactly matches the expected `68ef…` predecessor identity and that the replay/state database is preserved;
3. obtain a separate owner LIVE authorization for the fixed #607 capability-refresh target and exact source SHA;
4. run one refresh and verify broker/registration identity plus unchanged replay-state metadata;
5. only then create a new READY queue bound to the post-refresh exact source; `ops-workflows#69` remains stale historical evidence;
6. create a fresh direct-owner LIVE-AUTH with a new request identity; `ops-workflows#70` remains spent and non-reusable;
7. allow one v9 dispatch and verify the installed Weather operator module target hash;
8. only then resume Weather public-runtime rollout reconciliation.

None of these source contracts authorizes Docker application mutation, systemd Weather application restart, SQLite/corpus writes, cleanup/rollback of the partial Weather runtime, Cloudflare/network changes, secrets/credentials, or reuse of consumed Gate4 authorization #33.
