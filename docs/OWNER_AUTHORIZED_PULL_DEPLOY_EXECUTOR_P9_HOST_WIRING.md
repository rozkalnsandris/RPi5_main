# Owner-authorized deploy executor — P9 host runtime wiring source contract

Status: **SOURCE ONLY / DORMANT / NOT INSTALLED / NO P9 AUTHORIZATION**

This source gate closes the runtime-composition gap proven by the first Control P9 attempt after `RPi5_main#280`: the reviewed P9 modules existed in source, but the installed P8 package did not contain them, had no canonical P9 entrypoint, no dedicated P9 StateStore binding and no trusted evidence spool.

The gate deliberately does **not** install or activate anything on RPi5. Merge is source readiness only.

## Canonical runtime shape

P8 remains unchanged: its timer, service, unprivileged poller and existing state directory are not reused as a P9 execution surface.

P9 is a separate manual, owner-gated one-shot:

- executable: `/usr/local/sbin/rozkalns-deploy-p9`;
- fixed isolated-auth contract: `/etc/rozkalns-deploy-executor/executor-p9-isolated-auth-surface.json`;
- fixed execution-disabled registry: `/etc/rozkalns-deploy-executor/executor-operations.json`;
- Deploy Executor App credential: existing `/etc/rozkalns-deploy-executor/github-app.pem`;
- Rozkalns Automation source-read credential: existing root-controlled `/root/.config/rozkalns-automation/github-app.pem`;
- dedicated P9 replay DB: `/var/lib/rozkalns-deploy-executor-p9/state.sqlite3`, root-owned and not shared with the P8 poller;
- trusted evidence spool: `/run/rozkalns-deploy-executor-evidence`, `root:rozkalns-deploy-executor`, mode `0750`.

The P9 host composition contains no dispatcher, result writer, `StateStore.consume()` or adapter `apply()` path. The Control adapter remains preflight-only and the static registry must remain `execution_enabled=false`.

## Source/CI trust domain

LIVE-AUTH and READY reads stay on the isolated Deploy Executor App (`4748870`). Control source/CI evidence uses a distinct Rozkalns Automation provider (`4537106`) that requests one token for exactly repository ID `1329279953` with only `Actions: read` and `Contents: read` (plus implicit metadata read).

This source addition does not prove that the live Automation App installation currently includes Control Center. Adding that repository to the live App installation is a separate credential/permission-surface mutation and therefore a later explicit LIVE gate. The P9 provider fails closed if the installation or minted token does not provide exactly the reviewed read-only capability.

## Pre-StateStore gate

The canonical entrypoint performs a complete read-only duplicate preflight before constructing the StateStore mutation path:

1. isolated-auth contract remains dormant/fail-closed;
2. registry contains exactly the reviewed Control operation and is globally execution-disabled;
3. trusted Control baseline file is present through the fixed provenance loader;
4. LIVE-AUTH is accepted and queue binding is exact;
5. Control source identity/reachability/exact-SHA CI is verified with the separate source-read App;
6. baseline freshness/source binding is validated against GitHub server time;
7. Control adapter preflight remains read-only and privileged dispatch disabled;
8. LIVE-AUTH is re-fetched unchanged.

Only then is the existing durable StateStore opened and `run_p9_dry_run_canary()` allowed to reach its first `discover()` write. Any failure before that point leaves the P9 attempt unconsumed.

After the first StateStore mutation, normal fail-closed transaction rules apply: an error or drift is STOP with no automatic retry, rollback, cleanup or alternate mutation.

## Installer source contract

`scripts/install-deploy-executor-p9-runtime.sh` is a future LIVE-only upgrade action. It is exact-SHA pinned, requires the existing P8 identity, installs a fixed list of reviewed P9 modules, creates a fresh dedicated root-owned P9 StateStore and the fixed evidence spool, and refuses ambiguous pre-existing P9 roots.

It deliberately does not:

- modify/enable/start/reload any systemd unit or timer;
- create users/groups;
- copy, rotate or modify either GitHub App private key;
- produce trusted baseline evidence;
- widen a GitHub App repository installation or permission;
- run P9;
- invoke Control, D1, Cloudflare, dispatcher, result writer or adapter apply.

A future live installation therefore still requires an explicit owner authorization. After installation, trusted Control evidence production remains a separate reviewed/fresh prerequisite, and the genuine P9 run requires a **new** human LIVE-AUTH plus a new exact P9 dry-run authorization. Expired historical LIVE-AUTH issues must not be reused.

## Acceptance

Source acceptance requires tests proving the separate source-read App scope, rejection of write/unknown-repository capability, absence of dispatch/apply paths from host composition, exact fixed state/evidence paths, and installer non-activation properties. Normal repository CI remains authoritative after the PR is pushed.
