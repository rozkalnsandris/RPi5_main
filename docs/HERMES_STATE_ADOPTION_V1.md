# Hermes state and household adapter preparation — #1014

Status: **SOURCE ONLY / SEPARATE LIVE AUTHORIZATION REQUIRED**.

Revision #1034 replaces whole-file byte snapshots with metadata and SHA-256
records. Data reads, staging copies and destination verification use chunks of
at most 64 KiB. The combined raw/config ceiling is 4 GiB, raw files are capped
at 128 MiB and config files retain 32 MiB. These ceilings provide headroom for
the measured approximately 1.87 GiB data set and approximately 82.8 MiB largest
raw file; they are not a claim that future production state fits. The contract's
`file_bytes` is the default/config ceiling; `raw_file_bytes` overrides it only
for raw. Entry/depth limits and publication/identity policy are unchanged.

This supersedes #1025's 256 MiB combined in-memory design. Old launchers and
authorizations remain bound to their old limits and must not be edited or
reused. Prepare a new exact-source execution packet after review.

A later metadata-reconciliation review narrows one production mismatch observed
during the V4 apply preflight. Beneath the already source-user-owned `data/raw`
root, historical entries may be either source-user-owned or legacy `root:root`.
Legacy root-owned directories are accepted only as `0755`; legacy root-owned
regular single-link files are accepted only as `0644`. `.gitkeep` is the only
hidden raw entry allowed, only directly under the raw root, and only as a
zero-byte `0644` regular file. `config` remains source-user-owned only. The
observed owner/mode remains part of each source fingerprint and is revalidated
before and during copy, while destination ownership/mode policy is unchanged.
This source reconciliation does not authorize a LIVE rerun.

Revision #1018 corrects the destination raw-directory permissions required by
the existing UID:GID `1000:1000` scheduled collectors. It does not execute the
prepared operation or authorize the later API/collector cutover. Any older
launcher/source authorization must be replaced with an exact new one-shot.
The follow-up quiescence guard also requires the installed Netto, ALDI, EDEKA
and EDEKA-monitor units to be inactive with their timers disabled before a
one-time copy. No timer is changed by this operator.

Revision #1014 supersedes #990's registry baseline after the CV-only stats
registry update. This revision accepts only the exact CV-updated fixture;
it retained the original identity-provenance anchor and publication limits of
that revision; #1034 revises only the data byte ceilings and streaming mechanics.
The old Weather-rebind baseline and historical Hermes-only output are rejected.
Receipt schema and CLI flags are unchanged; exact-source authorization must bind
the revised operator and contract.

`scripts/prepare-hermes-state-adoption.py` handles the state left after the
create-only env operation: the private child already exists, while the Hermes
state destination and API adapter are absent. It prepares both trees and the
household adapter/registry in one bounded operation. It does not deploy the UI.

The older v1 adoption and v1–v4 prerequisite operators remain historical contracts,
not fallback paths for this layout. In particular, do not run a combined legacy
env/state installer against the already-created env child.

## Baseline and provenance

The frozen **identity ancestry** baseline remains
`bcaa7c6db2d2404acb587d78a2dca7a0f7a1bb17`. It is not the registry source revision.
Registry provenance is independently anchored at
`c53d5642a9b700c5c2a24df9382c45252bd443ab`; both anchors must be ancestors of
the exact authorized operator source.
The operator checks the exact public artifact hashes in
`ops/contracts/hermes-state-adoption-v1.json`:

- installed registry equals `ops/deploy/baselines/simple-deploy-targets-cv-stats-1000-v1.json`,
  SHA-256 `24e284a03f68c3843b629254ed1a944648e7b902ce36161a6ee7412cfe7c42d0`;
- installed Weather adapter and generic executor equal the reviewed source bytes;
- both Hermes API adapters, all old/new env stages and all adoption stages are absent;
- existing private parent is root:runtime-group `0750`, env child is root:runtime-group
  `0640`, regular, single-link, no POSIX ACL; env content is never read;
- existing state parent remains runtime-principal-owned `0700`; no parent creation,
  chmod or chown is allowed;
- fixed legacy `data/raw` and `config` roots are source-user-owned real `0755` dirs;
  only descendants of `data/raw` may use the narrowly bounded legacy root-owned
  metadata policy described below.

The new fixture is derived entirely from public source: apply
`ops/bin/rozkalns-cv-live-stats-rollout-1000::target_only_registry` to the frozen
`simple-deploy-targets-weather-rebind-v1.json`. This changes only the CV Compose
digest to `6f14d9cbe07b2c03c4e9e14172de4318c1e8d591b97dd595dd82aacb38b7f19c`.
The output is the tracked `ops/deploy/simple-deploy-targets-v1.json`, SHA-256
`fd804753594532ad2b6731428b4640c8f8b15758649e98c62259619cf4f90eca`.
Its only semantic difference from the CV-updated baseline is the Hermes Compose
filename/digest. CV, Weather, other targets and global settings are preserved.
The old fixture remains unchanged for historical/CV consumers. This public fixture
is not a production dump or permission to accept arbitrary registry variants.

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
structure: 4,096 entries, 4 GiB total across raw and config, 128 MiB per raw
file, 32 MiB per config file, 12 levels of depth. Each streaming read requests
at most 64 KiB and is bounded by the checked file size (plus one byte to detect
growth); the extra byte is never written to the destination.
Only regular single-link non-executable files and real directories are accepted.
`config` entries must remain source-user-owned. Under `data/raw`, source-user
ownership remains valid; historical `root:root` descendants are accepted only
when directories are exactly `0755` and regular single-link files exactly
`0644`. The raw root itself may not be root-owned. Hidden entries remain
rejected except a direct raw-root `.gitkeep`, which must be a zero-byte `0644`
regular single-link file. Symlinks, special files, group/other write access,
all other unexpected ownership/modes, ACLs, cross-device traversal and
key/database/backup suffixes are rejected. The config snapshot must contain a
nonempty regular `sources.json`. These are hard fail-closed ceilings, not
observations of production size.

Only bounded metadata/digest records are retained in memory, never the complete
file contents. Each record binds the still-open source-root descriptor, recorded
directory ancestry, file metadata, size and SHA-256. Before a staging copy,
ancestors are reopened descriptor-relatively without following symlinks and
compared with the original fingerprints. Each file is copied incrementally and
must match its recorded metadata and digest before the staged file is completed.
Root/ancestor fingerprints are rechecked after the copy. Static public artifacts
continue to use the existing at-most-128-KiB byte reader.

Core dumps are disabled; no content, filename listing, content hash or exception
text is printed. Source metadata and streamed content hashes are compared again
before each publication; staged/published content is independently streamed and
hashed against the same records. This is a point-in-time copy, not ongoing
synchronization with legacy collectors; quiescing or cutting over
collectors is outside this operation. The fixed collector timers must already be
disabled before data content is read, and a later API cutover still needs its
own collector-write/API-read proof.
Concurrent source writes cause STOP when detected, never silent merging.

Streaming bounds memory, not total I/O or duration: existing full revalidation
passes are retained. The replacement execution packet must allow a bounded
longer operator runtime (up to 3600 seconds), replacing the old launcher's
180-second budget in a newly pinned launcher, never by editing a frozen one.
It must check available disk against the actual copy plus DB dump/restore needs
and a margin before first mutation. An old 12 GiB free-space observation is not
automatically sufficient for the expanded worst-case copy budget. These are
preflight/packet requirements, not authorization to read or modify the host.

The only allowed publication paths are:

1. Absent `/var/lib/rozkalns-simple-deployer/hermes-deals`, containing `data/raw`
   and `config`, via fixed `.hermes-deals-prerequisites-v1.staged` sibling.
2. Absent `/etc/rozkalns-simple-deployer/compose/hermes-deals-household-api.yml`,
   via fixed `.hermes-deals-household-api.yml.adoption-v1.staged` sibling.
3. Existing `/etc/rozkalns-simple-deployer/targets.json`, replaced only after its
   exact baseline is revalidated, via fixed `.targets.json.hermes-adoption-v1.staged`.

Only new inodes receive ownership/mode changes. State directories outside
`data/raw` remain root:root `0755`; copied state files remain root:root `0644`;
static files remain root:root `0444`. The `data/raw` directory and all copied
subdirectories are root:collector-group `03775` (setgid, sticky, group-write),
while their copied files stay root:root `0644`. The operator requires the
passwd-resolved legacy collector account to have exact UID:GID `1000:1000`
before any data read or staging; this matches the reviewed scheduled collector
units' numeric `docker compose exec --user 1000:1000`. A collector can add new
snapshot files but cannot edit or remove root-owned copied snapshots. Config
stays read-only to collectors. This source correction does not change the
legacy collector units or prove their post-cutover container selection; those
remain separate activation gates. No source metadata is copied as privilege
bits. Stages use exclusive creation, descriptor-relative
no-follow operations and fsync. State and adapter publication use Linux
`renameat2(RENAME_NOREPLACE)`; registry replacement is atomic per file, **not** a
multi-file transaction. The registry's only semantic change is the Hermes compose
filename and its digest. Every other target, global execution setting and Hermes
non-compose setting stays identical. Existing env, identity, executor and Weather
artifact fingerprints are rechecked throughout. No legacy adapter is installed.

## Quiescence, partial failure and later activation

Generic SIMPLE-DEPLOY service/timer must be loaded, inactive/dead, with no job or
pending daemon reload; service static, timer disabled. The fixed `show --all`
property filter retains empty job fields, as required by the
[systemctl manual](https://www.man7.org/linux/man-pages/man1/systemctl.1.html).
The Hermes instance units
must either be absent or meet the same inactive/disabled contract. These checks run
before first staging, between publications and after verification. In `--apply`,
the four installed Hermes Netto, ALDI, EDEKA and EDEKA-monitor services must also be
loaded, static and inactive/dead; their timers must be loaded, disabled and
inactive/dead, with no jobs or pending daemon reload. This stricter check runs
before source data/config content is read and again at each apply revalidation.
The default read-only static check does not require collector timer quiescence. The
2026-10-14 read-only diagnostic found the Netto, ALDI and EDEKA collector
timers enabled and active, so the operator would stop on that observed state.
There are no systemd lifecycle commands. Directory locks serialize this operator only; they do
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

## Existing checkout and later one-shot decision

A failed earlier attempt may have left a root-owned source checkout while no
Hermes state/adapter/registry publication occurred. Keep that checkout and any
other evidence intact. Do not reuse its consumed authorization, rerun its
create-only launcher, update it in place, or clean it up.

After this revision is merged and exact-source CI passes, prepare one new
bounded owner decision for that merged SHA. If source placement is needed, use
one new required-absent root-owned `/opt/hermes-state-adoption-<exact-new-SHA>`
directory with full public history. Explicitly authorize its creation/fetch and
all protected reads/writes in that decision; root-owned metadata, canonical
origin, clean HEAD/tree, pinned artifact hashes and Git object equality must be
verified before executing checkout code with isolated `python3 -I -B`.
The existing historical checkout is neither changed nor used as a fallback.
A new path does not reset publication state: reject existing destinations/stages
and freshly revalidate the exact CV-updated installed baseline and every other
prerequisite. Unknown drift requires STOP, not baseline substitution.

Source merge alone does not authorize placement, protected inspection, state
copy, adapter/registry publication or UI activation. The first authorized
mutation consumes the new one-shot; preserve evidence on error without retry,
rollback, cleanup or an alternate checkout/installer.
