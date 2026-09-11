# Weather public runtime operator installer bridge

Issue #462 closes only the host-install bootstrap gap for the already reviewed
Weather Composite operator closure. This document describes source readiness;
it does not prove host installation and does not grant LIVE authority.

## Fixed source identity

The installer is source-only and is intended to run directly from the reviewed
successor checkout derivation:

`RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted`

The fixed source entrypoint is:

`RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted/ops/bin/rozkalns-weather-public-runtime-operator-install`

The entrypoint accepts zero caller arguments and uses isolated Python startup.
The installer derives its own checkout from the reviewed source location and
requires the checkout basename, exact reviewed GitHub origin, detached HEAD,
clean worktree and `HEAD == refs/remotes/origin/main`.

The ordinary manager checkout is never an install source. The legacy
`RPi5_main-weather-public-runtime-trusted` checkout remains immutable evidence
only and is never reset, updated, cleaned, removed or reused as install authority.

## Fixed 23-artifact closure

The machine contract remains
`ops/deploy/weather-public-runtime-operator-install.json`. The installer accepts
exactly the 23 source/destination/mode identities frozen there; the same list is
also hard-coded in the capability-specific installer module so a contract edit
cannot silently expand path authority.

Every source file must be a bounded single-link regular file and its bytes must
match the exact Git blob recorded at trusted `HEAD`. Destinations are limited to:

- `/usr/local/libexec/rozkalns-weather-public-runtime-operator`;
- `/usr/local/sbin/rozkalns-weather-public-runtime-operator`.

Ownership and modes remain fixed to the reviewed root-owned contract. No wildcard
copy, caller-selected destination, generic command, shell, argv, environment or
repository URL is accepted.

## Fail-closed publication transaction

The installer requires the final support root, final entrypoint and deterministic
source-SHA staging identities to be absent before the first install write. Files
are staged with the existing reviewed O_EXCL/O_NOFOLLOW root-file primitive and
verified against trusted-HEAD hashes before publication.

Publication order is deliberately fixed:

1. atomically publish the complete support tree with `RENAME_NOREPLACE`;
2. verify exact support-tree membership, ownership, modes and hashes;
3. atomically publish the operator entrypoint with `RENAME_NOREPLACE`;
4. verify entrypoint and support tree again.

Therefore a stop after support publication but before entrypoint publication
leaves only an inert support tree. There is no automatic retry, cleanup,
rollback, overwrite or alternate installation route. Any later recovery or
cleanup is a new owner decision.

## Explicit exclusions

This bridge does not create the successor checkout and does not mutate the
ordinary manager checkout. It does not invoke the installed Weather operator or
stage helper. It does not create helper activation, release materialization,
Docker resources, systemd units, SQLite schema/data, corpus backfills, credentials,
network/Cloudflare state, packages, users/groups or permission policy.

Source merge keeps `SOURCE_READY_INSTALL_DISABLED`; it does not prove
`host_installed=true` and does not authorize installation.

## Required future sequence

After source merge and exact-main CI validation, a separate owner LIVE gate must
bind the exact merged `RPi5_main` SHA, target `rpi5`, successor-checkout bootstrap
and this exact 23-artifact installation closure. The reviewed successor checkout
must first be created at that exact source identity. Only then may this zero-input
root installer be invoked through a capability-specific privileged boundary.

After installation, fresh read-only verification must prove the exact 23 installed
artifacts before any first Weather rollout is considered. The rollout itself still
requires a new human-authored Composite STRICT LIVE-AUTH and fresh queue/source/CI/
baseline revalidation. Operator installation is not rollout authorization.
