# Weather operator v7 privileged delivery

Status: SOURCE-ONLY / HOST CAPABILITY NOT INSTALLED  
Issue: `RPi5_main#543`  
Operation: `rpi5-main.weather-operator-upgrade-v7.v1`

## Purpose

This source contract closes the Weather operator-v7 delivery gap without giving the conversational agent `sudo`, a generic root shell, or caller-selected command/path/argv/environment authority. The only caller-controlled privileged-boundary payload is the existing identity-only `rozkalns.deploy-dispatch-request.v1` authorization/request identity. The privileged side must independently revalidate the canonical owner authorization, queue/source/CI evidence and fixed operation identity before any later host mutation can begin.

The current installed P8 poller is evidence-only for this lane. **P8 remains mutation-disabled** and is not the Weather v7 privileged executor. `ops/deploy/weather-public-runtime-operator-upgrade-v7-privileged-delivery.json` therefore reports `SOURCE_READY_HOST_CAPABILITY_INSTALL_REQUIRED`: source readiness and host capability installation are separate states.

## Frozen operation

The source operation is `STRICT` and never ordinary `LIVE-ALL` eligible. It binds:

- repository `rozkalnsandris/RPi5_main`;
- target alias `rpi5-main-weather-operator-upgrade-v7`;
- fixed entrypoint `ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v7`;
- fixed destination `/usr/local/sbin/rozkalns-weather-public-runtime-operator`;
- predecessor SHA-256 `4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f`;
- target SHA-256 `f6255bf1e80d2918555b0814b0690add739041ac11512297d904fce5e8fc0cf1`;
- v7 checkout `RPi5_main-weather-public-runtime-operator-upgrade-v7-trusted`;
- preserved v6 checkout `RPi5_main-weather-public-runtime-operator-upgrade-v6-trusted`.

The future mutation budget is exact and cannot expand:

1. `git.weather-operator-upgrade-v7-checkout-fetch`: maximum 1;
2. `git.weather-operator-upgrade-v7-checkout-worktree-add`: maximum 1;
3. `filesystem.weather-operator-upgrade-v7-atomic-replace`: maximum 1.

No cleanup, retry, rollback, worktree remove/prune/repair, alternate privileged transport, Docker/systemd application mutation, SQLite/corpus mutation, network/Cloudflare mutation, credentials/secrets mutation or arbitrary execution authority is part of this operation.

## Trusted checkout boundary

The checkout bootstrap remains canonical in `ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v7-trusted-checkout-bootstrap.json`. A later owner-authorized execution may perform only one reviewed `git fetch origin main` and one fixed detached `git worktree add` after proving fresh `origin/main` equals the exact authorized SHA and that the SHA descends from the reviewed ancestor.

Every earlier trusted checkout, including v6, remains immutable evidence. v6 mutation, cleanup and use as authority are all false. A mismatch after mutation starts is a STOP condition; it does not create cleanup or repair authority.

## Identity-only privileged boundary

`ops/lib/deploy_executor/weather_operator_upgrade_v7_privileged_delivery.py` consumes only the authorization/request identity parsed by `ops/lib/deploy_executor/dispatch_contract.py`. It has no filesystem mutation, subprocess, package-manager, systemd, Docker or generic root execution surface. The canonical revalidator supplies and double-checks the source SHA, operation, adapter, target, authorization class, mutation budget, queue state, CI state and replay state. Sanitized host evidence supplies only the bounded checkout/operator identity needed to distinguish readiness states.

The source planner can return only:

- `HOST_CAPABILITY_INSTALL_REQUIRED` — source is ready but the narrow privileged host capability is not installed;
- `FUTURE_LIVE_CHECKOUT_BOOTSTRAP_READY` — host capability is proven but the v7 checkout is still absent;
- `FUTURE_LIVE_FIXED_OPERATOR_READY` — host capability and exact detached-clean v7 checkout are proven.

None of those source states performs a mutation or grants LIVE authority.

## Issue #571 one-time host-capability installer

`RPi5_main#571` adds the missing source-only installation boundary. Its machine contract is `ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-installer.json`, the default installer command is the read-only `scripts/install-weather-operator-v7-host-capability.py` preflight, and the source state is `SOURCE_READY_FOR_HOST_CAPABILITY_INSTALL`.

The installer is first-install-only. A later separately authorized root execution with `--apply` may install the isolated Weather-v7 support package, an identity-only systemd socket/broker, a dedicated replay-state database and a root-owned registration, then `daemon-reload` and enable/start only the fixed Weather-v7 socket. The install gate does **not** create the v7 checkout, replace the Weather operator, deploy the Weather application, alter SQLite/corpus data, change Cloudflare/network state, or enable global/P8 mutation dispatch.

The installed broker accepts only `rozkalns.deploy-dispatch-request.v1`. It independently requires a fresh owner/TTL-bound Weather-v7 authorization issue, a separate matching open `READY` deploy-queue issue, exact current `RPi5_main` source/CI, the reviewed predecessor hash, preserved v6 checkout and its own root-owned registration. Only after durable one-shot replay consumption may it use the frozen maximum budget of one `git fetch`, one detached v7 `git worktree add`, and one zero-argument v7 operator replacement. Caller-selected command, path, argv, environment, repository, source SHA, target and mutation plan are not accepted.

A successful source merge changes only the source state from “installer missing” to `SOURCE_READY_FOR_HOST_CAPABILITY_INSTALL`; it does not claim `HOST_CAPABILITY_INSTALLED`. The latter requires sanitized read-only evidence after the separately authorized host installation.

## Issue #574 trusted installer source delivery

`RPi5_main#574` defines the source-only bootstrap required because the #571 installer itself must run from a clean exact `RPi5_main` checkout while the long-lived manager checkout may legitimately be stale or dirty. The machine contract is `ops/deploy/rpi5-main-weather-v7-host-capability-installer-source-trusted-checkout-bootstrap.json`.

The dedicated checkout identity is `RPi5_main-weather-v7-host-capability-installer-source-trusted`. It is intentionally distinct from the later operator-upgrade checkout `RPi5_main-weather-public-runtime-operator-upgrade-v7-trusted`; neither checkout can serve as authority for the other gate. The manager checkout may remain dirty, but its working tree, index and HEAD are outside mutation authority.

A later exact owner LIVE authorization for source delivery may allow at most one `git fetch origin main` followed by one detached `git worktree add` at the exact owner-authorized current `RPi5_main` SHA. Before worktree creation, fresh `origin/main` must equal that SHA and the exact-main required checks must be successful. Preflight state is exactly `ABSENT`, `EXACT_CLEAN` or `CONFLICT`; any conflict fails closed without cleanup, reset, stash, prune, repair or alternate target.

Successful source delivery grants no authority to run `--apply`. It only creates the exact clean source from which `scripts/install-weather-operator-v7-host-capability.py` can later be re-preflighted and, under a separate host-install LIVE gate, executed. The source-delivery gate cannot install the capability, mutate systemd, create the later operator-v7 checkout, replace the operator, deploy Weather or mutate DB/corpus/network/secrets.

## Issue #586 sudo Git trust correction

The first owner `sudo ... --apply` attempt from the #574 trusted checkout failed inside `preflight()` before `mutation_started` because the installer intentionally supplied Git a minimal environment but accidentally omitted sudo's `SUDO_UID`. Git's ownership protection therefore treated the user-owned trusted worktree as foreign when Git ran as root and rejected `git rev-parse HEAD` with exit 128. No capability, systemd, replay-state, operator or Weather mutation started.

The correction keeps the Git child environment minimal and adds only a validated decimal `SUDO_UID` when the installer itself is running as root. It does not inherit arbitrary sudo/user environment variables, does not add `safe.directory=*`, does not write Git configuration and does not change repository ownership or permissions. Invalid or reserved `SUDO_UID` values fail closed before any host mutation.

The original #574 checkout remains immutable evidence and must not be updated, removed, cleaned or reused for the corrected source. The corrected source-delivery identity is `RPi5_main-weather-v7-host-capability-installer-source-v2-trusted`, governed by `ops/deploy/rpi5-main-weather-v7-host-capability-installer-source-v2-trusted-checkout-bootstrap.json`. A later owner LIVE gate must materialize that new checkout at the then-current exact merged `RPi5_main` SHA before the host-capability install is retried.

## Owner gate order

The required order is intentionally explicit:

1. **source merge + exact-main CI** for the reviewed `RPi5_main#543`, `RPi5_main#571`, `RPi5_main#574` and `RPi5_main#586` source outcomes;
2. a separate owner-gated **corrected exact-main #571-installer v2 source delivery** if the v2 checkout is absent;
3. **sanitized source-checkout verification** proving exact SHA, detached-clean state and reviewed origin;
4. a separate owner-gated **one-time privileged-boundary host install/upgrade**, if sanitized evidence still reports the capability absent;
5. **sanitized capability verification** proving the fixed capability identity without protected runtime data;
6. a **fresh exact Weather v7 LIVE authorization** binding the then-current reviewed `RPi5_main` SHA, fixed target, predecessor identity and exact 1+1+1 mutation budget;
7. **installed-closure verification** proving the new operator SHA-256 and `root:root 0755`, with v6 still preserved;
8. return to **rozkalns_weather public rollout reconciliation** before any Weather application rollout.

**Source merge does not authorize LIVE.** Trusted installer source delivery, host capability installation and the later Weather v7 operator execution remain separate owner gates. None authorizes the public Weather rollout, Docker/systemd application changes, database/corpus writes, Cloudflare/network changes or private WeatherNext credentials.

## Fail-closed semantics

Authorization is consumed at the first authorized mutation. After that point, source/head/CI/baseline drift, checkout mismatch, predecessor mismatch, transport failure, replacement failure or verification failure permits only minimum sanitized read-only evidence followed by STOP. There is no automatic retry, cleanup, rollback, backup restore or alternate mutation path.
