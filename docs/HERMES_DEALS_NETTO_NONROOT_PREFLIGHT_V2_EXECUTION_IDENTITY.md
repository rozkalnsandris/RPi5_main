# Hermes Deals Netto v2 — fixed non-root/no-Docker execution identity

## Scope

This document defines the source-only execution-identity boundary that follows the successful
first installation of the frozen Netto non-root preflight v2 helper. It does not authorize helper
execution, a canary, systemd/socket wiring, broker installation, or any host/runtime mutation.

The installed helper remains bound to Hermes source
`067db7bd4b8057bc16a9bf0ef9ed8487127a0a05` and SHA-256
`275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c`.

## Fixed process surface

`ops/lib/deploy_executor/hermes_deals_netto_nonroot_preflight_v2_helper_launch.py` defines one
capability-specific process surface:

- interpreter: `/usr/bin/python3`;
- helper:
  `/usr/local/libexec/hermes-deals-audits/netto-missing-normal-price-nonroot-preflight-v2/netto_missing_normal_price_nonroot_preflight_v2.py`;
- argv: interpreter, fixed helper path, frozen registered source SHA;
- cwd: `/home/andris`;
- uid: `1000`;
- gid: `1000`;
- supplementary groups: empty;
- shell: false;
- environment: source-fixed minimal mapping.

There is no caller-controlled command, path, argv, environment, uid, gid, supplementary-group
list, cwd, shell, service, socket or capability selector.

## Why UID/GID 1000 with no supplementary groups

The helper must access fixed corpus and manifest paths owned by the normal RPi5 account, while the
normal account currently has Docker-group authority. A future root parent may therefore drop the
child to UID/GID 1000 and explicitly set `extra_groups=()` before `exec`. This preserves ordinary
owner filesystem access without inheriting Docker supplementary-group authority.

This source contract does not alter the user, group database, ACLs, Docker membership or file
ownership.

## Helper provenance gate

Before any future process launch, the launcher validates the installed helper as:

- regular and not a symlink;
- exactly one hard link;
- `root:root`;
- mode `0555`;
- exact SHA-256
  `275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c`;
- descriptor identity matching the path observed before the read.

The fixed file is opened read-only with no-follow semantics where supported.

## Source readiness only

The merged source must remain:

- `launch_enabled=false`;
- `host_wiring_enabled=false`;
- `canary_authorized=false`;
- `production_mutation_started=false`.

The existing Netto adapter and operation registry remain execution-disabled. This launcher module
is not connected to `apply()` in this slice.

## Future gates

After merge and exact-main CI, any host wiring that gives a root parent access to this fixed
launcher is a separate source/trust-boundary decision and a separate LIVE authorization. A genuine
Netto helper invocation/canary is another independent READY/LIVE-AUTH gate after host wiring is
proven.

Merge does not authorize host wiring. Host wiring does not authorize a canary. No source step in
this document authorizes runner retirement.
