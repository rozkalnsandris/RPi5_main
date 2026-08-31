# Owner-authorized deploy executor — P9 source-App repair host upgrade

Status: **SOURCE ONLY / LIVE HOST UPGRADE NOT AUTHORIZED BY MERGE**  
Roadmap: `RPi5_main#236`  
Canonical continuation: `RPi5_main#191`

## Purpose

This repair closes the P9 source-App ambiguity discovered after the baseline wiring work without widening runtime authority.

The reviewed source changes do two things:

1. prove the exact `rozkalnsandris/rozkalns-control-center` repository installation with an App JWT before any installation-token mint; and
2. provide a narrow future host-upgrade operator for the two already-installed files that must move from the reviewed pre-repair runtime bytes to the reviewed repaired source.

No repository selection, GitHub App permission, credential, D1, host/runtime, service or production mutation is performed by this source change.

## Repository-specific source-App proof

Before minting a source token, `p9_source_auth.py` performs:

`GET /repos/rozkalnsandris/rozkalns-control-center/installation`

using the source App JWT.

The response must prove all of the following before token mint:

- installation ID exactly `152422751`;
- App ID exactly `4537106`;
- target ID exactly `277435981` and target type `User`;
- account login exactly `rozkalnsandris`, account ID exactly `277435981`, account type `User`;
- `repository_selection=selected`;
- `actions=read` and `contents=read`;
- optional `metadata=read`;
- no additional permission key and no non-read permission.

A 404, non-object response, wrong identity, missing permission, unexpected/write permission or selection ambiguity fails closed before token mint. Public failure output remains limited to the pre-existing allowlisted source-token stage names; HTTP response bodies and inner exception text are not exposed.

The minted token response must independently retain `repository_selection=selected`, the exact read-only permission set and exactly the Control Center repository ID/name.

## Reviewed host-upgrade operator

The source-only operator is:

`python3 scripts/install-deploy-executor-p9-source-repair-upgrade.py <exact-reviewed-rpi5-main-sha>`

Without `--apply`, it is preflight-only and performs no filesystem mutation.

A future invocation with:

`python3 scripts/install-deploy-executor-p9-source-repair-upgrade.py <exact-reviewed-rpi5-main-sha> --apply`

is a separate LIVE host mutation and requires explicit owner authorization at that time. Source merge never authorizes `--apply`.

### Exact old installed prestate

Both targets must exist as regular, non-symlink root-owned files and match the reviewed old Git blob exactly:

| Target | Expected metadata | Reviewed old blob |
| --- | --- | --- |
| `/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py` | `root:root 0644` | `b4dc3e3b4662c5f8606817fe453ce5bfb907db3e` |
| `/usr/local/sbin/rozkalns-deploy-p9-control-baseline` | `root:root 0755` | `210815b33e47fb843f71473f485b87e0b751b59d` |

These hashes are expected future upgrade prestates only. They do not assert current host/runtime state.

The operator also requires:

- root execution;
- local checkout `HEAD` exactly equal to the supplied reviewed SHA;
- the operator working-tree file unchanged from that exact SHA;
- both replacement byte streams loaded from Git objects at that exact SHA;
- every parent component of both target paths to be a real root-owned directory that is not group/world writable;
- the complete prestate for both installed targets to pass before the first mutation;
- a duplicate source/prestate gate immediately before `--apply` begins mutation.

Any mismatch is STOP before mutation.

### Mutation envelope

After the final duplicate gate, the only writable targets are the two paths above.

Each target is opened in place with no-follow protection, its opened inode/metadata/old bytes are revalidated, and only then is that exact opened file truncated and rewritten with the reviewed Git-object bytes. Fixed modes and `root:root` ownership are reasserted, the file is fsynced, and the written bytes are re-read from the same descriptor for exact post-write verification.

There is deliberately no temp-file/rename path, cleanup, rollback, retry or alternate mutation path. If an error occurs after the first truncate/write begins, preserve evidence and STOP under the project fail-closed rule.

The operator does not:

- make GitHub, Cloudflare, D1 or other network requests;
- read, create, rotate or modify credentials/private keys/tokens;
- run baseline collection or P9 execution;
- open or mutate the P9 StateStore;
- change P9 config/registry;
- invoke `systemctl` or change services/timers;
- change packages, networking, firewall, DNS, containers, users/groups or sudo policy.

## Status markers

A successful preflight-only run prints:

- `P9_SOURCE_REPAIR_UPGRADE_PREFLIGHT=PASS`;
- `P9_SOURCE_REPAIR_MUTATION=NO`.

A successful separately authorized `--apply` run prints:

- `P9_SOURCE_REPAIR_UPGRADE=PASS`;
- `TARGETS_REPLACED=2`;
- `NETWORK_REQUEST=NO`;
- `CREDENTIAL_READ=NO`;
- `P9_EXECUTION=NO`;
- `STATE_STORE_TOUCHED=NO`;
- `SYSTEMD_MUTATION=NO`;
- `CONFIG_REGISTRY_MUTATION=NO`;
- `ROLLBACK_PATH=NO`.

## Activation boundary

Merge of this repair proves source readiness only. It does not prove that the RPi5 host contains these files, does not authorize the host upgrade, does not place the Control D1 credential, does not authorize baseline collection and does not authorize a P9 dry run.

Any future host `--apply`, credential placement, source-App live proof, D1 baseline collection or genuine P9 execution remains a separate owner-gated LIVE action with fresh evidence and authorization.
