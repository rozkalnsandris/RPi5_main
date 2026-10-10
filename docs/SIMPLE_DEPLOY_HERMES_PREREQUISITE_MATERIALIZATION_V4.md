# Hermes v4 — shared private-parent compatibility (#958)

**SOURCE-ONLY / NO APPLY / CONSUMER ACCESS NOT PROVEN**

V4 is an additive, metadata-only Hermes Deals successor; existing v1/v2/v3
materializers, tests, contracts and the preserved failed trusted checkout stay
untouched. The existing Weather private-parent trust boundary is authoritative
for this source design. This file does not provide a host authorization.

## The two independent permission checks

The installed shared parent is a real directory at
`/etc/rozkalns-simple-deployer/private` with owner
`root:rozkalns-simple-deployer` and mode `0750`.
V2 and v3 instead require `root:root` and `0700`. Do not create,
rename, chown, chmod, remove, replace or follow a symlink for that shared
parent. A mismatch is `PARTIAL_CONFLICT`; missing parent is not
permission to create it.

The SIMPLE-DEPLOY service runs under the unprivileged
`rozkalns-simple-deployer` principal. Compose consumes a fixed Hermes Deals
`env_file` on the host. V3 produces a root-owned private child in mode
`0600`, which cannot be assumed readable by the Compose client.
Directory search access and file read access are separate permissions.

The **candidate only** child-file access design is a single fixed
`hermes-deals-api.env`, root-owned with primary group
`rozkalns-simple-deployer` and mode `0640`. That would not grant world
read access or change other private children. However, group readability
could reveal the env to any *other* member of the runtime group. V4
conservatively checks the runtime group's local NSS supplementary members
and passwd primary-group members and rejects extra members or unknown
identity. This check alone cannot prove every runtime, NSS, Compose or
future trust condition. **No new group or permission is authorized.**

The exact parent and candidate child metadata are verified using fixed
path `lstat`-based checks. V4 does not open protected env data, inspect
Docker, read raw runtime configuration, verify secret equivalence or grant
permission changes. The child must be regular, one link, root-owned and
exactly mode `0640` to classify `EXACT_READY`. This is metadata-only
readiness **not** deployment readiness.

## Strict results and CLI

The only CLI input is `--expected-source-sha` and it inherits v3's
source checkout HEAD, clean tree, origin, exact Git blobs and non-writing
Git checks (`--no-optional-locks` and `GIT_OPTIONAL_LOCKS=0`).
There is deliberately **no** `--apply` option, no materializing
code path, no cleanup, rollback or retry path.

- `ABSENT`: fixed children absent, but parent metadata exact.
- `EXACT_READY`: metadata and fixed child shape match the **candidate**.
- `PARTIAL_CONFLICT`: mismatched parent, child, group, path or staging.
- `PRIVILEGED_METADATA_REQUIRED`: fixed metadata inaccessible.

All outcomes force `activation_eligible=false`,
`apply_available=false` and `protected_content_read=false`.
Do not silently call v2/v3 apply or manufacture a new LIVE permission
path under this source change.

A separate owner decision and a new reviewed source outcome are required
before any future child-file permission/trust-boundary change and actual
protected materialization. That later proposal must verify the actual
Compose process identity, no unauthorized supplemental group members,
race-free metadata checks, source integrity, STOP-on-error semantics and
a distinct prerequisite/adoption deployment transaction.

Timer restore #60 remains **BLOCKED_NO_START** until all nine gates and
all five targets are independently verified. This source PR neither
installs the v4 script on the host nor updates the generic executor,
registry, Compose file, systemd service or timer.

Official documentation:
- https://man7.org/linux/man-pages/man7/path_resolution.7.html
- https://docs.docker.com/reference/compose-file/services/
- https://man7.org/linux/man-pages/man5/systemd.timer.5.html

**Production deploy/change REQUIRED: NO.**
