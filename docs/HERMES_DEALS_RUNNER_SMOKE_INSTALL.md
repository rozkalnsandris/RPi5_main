# Hermes Deals runner-smoke capability-specific install

Issue: `RPi5_main#476`

## Source outcome

This source package closes the missing runner-smoke installation boundary identified after `#472` / PR `#473`. It does not install or execute anything on RPi5.

The capability is `hermes-deals.runner-smoke-audit.v1`. Its future canary target is `hermes-deals-runner-smoke-audit`; the first separate LIVE gate is `hermes-deals.runner-smoke-audit.install.v1` targeting `hermes-deals-runner-smoke-audit-install`.

Reviewed Hermes Deals source is `0e3b834f155cef7f9e964ddf02228c6a7ad1950c`; runner-smoke workflow blob is `c9107e7597ff3ce1214cb32fb740346fa9d190aa`. Source state is not runtime state.

## Fixed trust boundary

The only execution identity is `hermes-deals-audit-canary`: system account, primary group of the same name, home `/nonexistent`, shell `/usr/sbin/nologin`, non-root, no Docker group and no supplementary groups.

Helper destination: `/usr/local/libexec/rozkalns-deploy/hermes-deals-runner-smoke-audit`, root-owned `0755`, SHA-256 `fc8ccc8a2179c23670d28bbe166e45f85769b8bd13c319e423f56c4f65b17bd4`.

Registration destination: `/etc/rozkalns-deploy/hermes-deals-runner-smoke-audit.json`, root-owned `0644`, SHA-256 `3bc7771d8480ac3a5a5de6ab7f0eb6710cf3aaa458c8a60eaffb5c8d8aaf5c10`.

No caller may select command, executable path, destination path, argv, environment, account, group or mutation sequence. Existing exact state is idempotent; symlink, non-regular, wrong-owner, wrong-mode, wrong-content or otherwise conflicting state is `BLOCKED`.

## PLAN and APPLY

`build_plan()` is read-only and accepts only merged/reachable + exact-SHA CI evidence and `ABSENT`/`EXACT` state for the dedicated identity/helper/registration. It never consumes LIVE authority.

`apply_install()` is source-implemented but has no externally enabled entrypoint. A future wrapper must supply a canonical LIVE envelope bound to owner numeric identity, exact operation/gate/target, exact Hermes SHA, exact merged RPi5_main SHA, both CI proofs, fixed artifact hashes, canonical request-body hash, identical refetch, TTL validity and replay availability.

If all state is exact, APPLY returns no-mutation without consuming authorization. Otherwise authorization is consumed immediately before the first fixed mutation. After consumption there is no automatic retry, cleanup, rollback or alternate mutation path; `rollback_policy=NONE`.

The fixed mutation sequence may only create the exact dedicated system group/user if absent and install the two exact root-owned artifacts with no-follow/no-overwrite semantics. The installer never invokes the helper.

## Helper output and canary receipt

The helper emits only sanitized `rozkalns.hermes-deals.runner-smoke-helper-output.v2` runtime observation and intentionally contains no authorization metadata. A later separately reviewed LIVE wrapper must compose canonical `rozkalns.hermes-deals.runner-smoke-canary-evidence.v1` from authentic authorization plus runtime evidence. Synthetic PASS is forbidden.

## Static operation

`ops/deploy/executor-operations.json` registers `hermes-deals.runner-smoke-audit.v1` as `STRICT`, `ordinary_live_all_eligible=false`, `rollback_policy=NONE`, with one read-only invocation maximum. Global `execution_enabled` remains `false`.

## Later LIVE gate

Source merge is not LIVE authorization. Before any installation, freshly prove exact merged `RPi5_main` SHA + exact-main CI, exact Hermes Deals SHA + exact-SHA CI, fixed artifact identities, destination/account state, and a separate owner LIVE authorization for `hermes-deals.runner-smoke-audit.install.v1`.

This source package creates no READY item, LIVE-AUTH issue, replay consumption, helper invocation, systemd/service/Docker/network/credential/database/production/runner mutation or synthetic runtime evidence.
