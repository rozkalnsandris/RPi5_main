# Hermes state and household adapter preparation — #990

Status: **SOURCE ONLY / SEPARATE LIVE AUTHORIZATION REQUIRED**.

`scripts/prepare-hermes-state-adoption.py` handles the state left after the
create-only env operation: the private child already exists, while the Hermes
state destination and API adapter are absent. It prepares both trees and the
household adapter/registry in one bounded operation. It does not deploy the UI.

The older v1 adoption and v1–v4 prerequisite operators remain historical contracts,
not fallback paths for this layout. In particular, do not run a combined legacy
env/state installer against the already-created env child.

## Baseline and provenance

The frozen source baseline is `bcaa7c6db2d2404acb587d78a2dca7a0f7a1bb17`.
The operator checks the exact public artifact hashes in
`ops/contracts/hermes-state-adoption-v1.json`:

- installed registry equals the frozen pre-household Weather-rebind fixture;
- installed Weather adapter and generic executor equal the reviewed source bytes;
- both Hermes API adapters, all old/new env stages and all adoption stages are absent;
- existing private parent is root:runtime-group `0750`, env child is root:runtime-group
  `0640`, regular, single-link, no POSIX ACL; env content is never read;
- existing state parent remains runtime-principal-owned `0700`; no parent creation,
  chmod or chown is allowed;
- fixed legacy `data/raw` and `config` roots are source-user-owned real `0755` dirs.

The preceding hash-only probe did not recognize `identity.json`. That is not proof
of corruption. This operator parses only the bounded static identity file, rejects
extra/duplicate keys and requires the exact SIMPLE-DEPLOY schema/repository plus
a full source SHA proven by local public Git history to be an ancestor of the
frozen baseline above. It emits only `PUBLIC_BASELINE_ANCESTOR_PRESERVED`, never the
raw identity or an unknown hash. This establishes public source provenance only;
it does **not** assert that all installed files came from that revision. Installed
registry, Weather and executor identity are checked independently against exact
bytes. Identity bytes, inode and metadata are preserved, never rewritten to make
a check pass. Unknown provenance or missing Git history stops before any write.

Source preparation must supply complete history through the frozen baseline in a
root-owned, non-writable-to-others checkout with canonical origin and exact clean
reviewed HEAD. The launcher must verify checkout/script/Git metadata trust **before**
executing Python, using isolated `python3 -I -B`. A shallow clone lacking ancestry
proof is insufficient. No package installation, source fetch or checkout creation
is performed by this operator. If needed, the future authorization must explicitly
include that preparation. Git checks suppress optional index writes and replace
objects; no user-writable Python module is imported.

## Read and write envelope

Default invocation takes only `--expected-source-sha`. It verifies source,
fixed-path metadata, four static installed files (identity, registry, Weather
adapter, executor; at most 128 KiB each) and allowlisted systemd status properties.
It does not recurse into or read source data/config files. Success is
`BASELINE_CHECKED_DATA_UNREAD`; it does not prove that copying can succeed.
Privileged/static-runtime inspection itself still needs the applicable exact
owner authorization. Source merge or START is not that authorization.

`--apply` additionally reads only the passwd-resolved `andris` source checkout's
`data/raw` and `config` trees. It never opens the sibling `.env`, Docker storage,
database or backup trees. Bounds apply across both trees and fixed destination
structure: 4,096 entries, 256 MiB total, 32 MiB per file, 12 levels of depth.
Only regular single-link non-executable files and real directories are accepted;
symlinks, special files, group/other write access, unexpected ownership, ACLs,
cross-device traversal, hidden entries and key/database/backup suffixes are rejected.
These are hard fail-closed ceilings, not observations of production size.

The complete bounded snapshot is held in memory. Core dumps are disabled; no
content, filename listing, content hash or exception text is printed. Source
metadata and bytes are compared again before each publication. This is a point-in-time
copy, not ongoing synchronization with legacy collectors; quiescing or cutting over
collectors is outside this operation and must be addressed before runtime activation.
Concurrent source writes cause STOP when detected, never silent merging.

The only allowed publication paths are:

1. Absent `/var/lib/rozkalns-simple-deployer/hermes-deals`, containing `data/raw`
   and `config`, via fixed `.hermes-deals-prerequisites-v1.staged` sibling.
2. Absent `/etc/rozkalns-simple-deployer/compose/hermes-deals-household-api.yml`,
   via fixed `.hermes-deals-household-api.yml.adoption-v1.staged` sibling.
3. Existing `/etc/rozkalns-simple-deployer/targets.json`, replaced only after its
   exact baseline is revalidated, via fixed `.targets.json.hermes-adoption-v1.staged`.

Only new inodes receive ownership/mode changes: state directories root:root `0755`,
state files root:root `0644`, static files root:root `0444`. No source metadata is
copied as privilege bits. Stages use exclusive creation, descriptor-relative
no-follow operations and fsync. State and adapter publication use Linux
`renameat2(RENAME_NOREPLACE)`; registry replacement is atomic per file, **not** a
multi-file transaction. The registry's only semantic change is the Hermes compose
filename and its digest. Every other target, global execution setting and Hermes
non-compose setting stays identical. Existing env, identity, executor and Weather
artifact fingerprints are rechecked throughout. No legacy adapter is installed.

## Quiescence, partial failure and later activation

Generic SIMPLE-DEPLOY service/timer must be loaded, inactive/dead, with no job or
pending daemon reload; service static, timer disabled. The Hermes instance units
must either be absent or meet the same inactive/disabled contract. These checks run
before first staging, between publications and after verification. There are no
systemd lifecycle commands. Directory locks serialize this operator only; they do
not claim to lock the generic executor. The exact LIVE window must exclude other
manual deployment/adoption writers; unexpected path/inode/content changes stop.

The first mkdir attempt marks mutation as attempted. Any exception, interrupt,
size limit, drift, or uncertainty stops with a sanitized receipt. Stages and any
published objects remain as evidence. There is **no retry, rollback, deletion,
cleanup or alternate installer**. A failed run needs a new exact owner recovery
decision. Do not rerun apply even if only the state or adapter was published.

Success is `PREPARED_NO_ACTIVATION`, with three publication booleans and
`activation_eligible=false`. No Docker/Compose, image pull, HTTP request, Nginx,
DB/schema/migration, collector, timer start or service restart is performed.
The existing `home` household/origin source settings do not prove live household
identity, DB readiness or access. Non-default live household/origin must still stop
later activation until explicitly reconciled. UI rollout requires its separate
exact release, backup/restore, schema, ingress, state freshness and canary gates.
Hermes stays fleet-last; do not restore timers because files were prepared.

## Delivery and operator decision

One source issue/branch/PR contains the operator, machine contract, synthetic tests
and this runbook. Run `python3 tests/test-hermes-state-adoption.py`, the existing
Hermes/Weather compatibility tests and repository guards/CI before the exact-head
owner MERGE gate. Tests use temporary synthetic files only.

After merge and exact-main CI, prepare one concrete Composite LIVE decision binding
that merged SHA, rpi5, the operator/launcher identities, static protected reads,
bounded source data/config reads and the three publications above. Include trusted
checkout preparation explicitly if required. Revalidate current source and baseline
before dispatch. Neither this document, its tests nor a successful source merge
is authorization to execute that operation.
