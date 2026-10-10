# SIMPLE-DEPLOY executor single-file upgrade operator (#933)

**Source-only / Draft PR.** The issue explicitly ends at **Ready**. It grants
**no merge, RPi5 checkout change, service/timer operation, Docker/Buildx
execution, CV receipt/registry/Compose change, credential read, or LIVE apply.**

## Fixed source and target identities

Only the installed *public executor Python source file* may be replaced in a
later separately authorized STRICT LIVE action:

| Role | Fixed path / identity |
|---|---|
| Installed target | /usr/local/libexec/rozkalns-simple-deployer/simple_deploy_v1.py |
| Reviewed baseline SHA-256 | bec054249e6729f6a5a87516758fda77d5382d5b18c37318ec7b953d36422af2 |
| Git-reviewed desired source | ops/lib/deploy_executor/simple_deploy_v1.py |
| Reviewed commit | c0861f8fb4c8ea1df73fcffc340323d7d846641a |
| Reviewed Git blob SHA-1 | 8ef118030c8c83b8b713d93a80d5710fa6f79f3c |
| Desired SHA-256 | ed906786fd85169c6c555a3ac466b157edaf24a65fe12f60ee2ec6940ade20d0 |
| Root-owned offline source candidate | /usr/local/share/rozkalns-simple-deployer-issue933.py |
| Reviewed source operator | ops/bin/simple-deploy-executor-upgrade-933 |
| Root-installed operator (separate LIVE gate) | /usr/local/sbin/simple-deploy-executor-upgrade-933 |
| Separate owner LIVE proof | /run/rozkalns-simple-deployer-issue933-approval.json |

The candidate is **not downloaded, obtained, staged or installed** by this
source PR/operator. Before any future CHECK, an independent, exact source
preparation action must put the reviewed immutable Git object bytes at that
fixed root-owned candidate path as regular one-link mode **0444**, and verify
both the SHA-256 and Git blob SHA-1. This preparation is itself a distinct
owner-gated LIVE file write. The operator cannot accept caller-specified
URLs, blobs, branch names, directories, alternate files or alternate SHA
values. The Git commit and blob identity are frozen in reviewed source.

The installed destination must already be a root-owned regular one-link file,
**0444**, matching the pinned baseline hash. Its parent directory must be
root-owned and not group/world writable. No host user checkout or running CV
image is changed in the source phase or by the future operator.

## CHECK is the default; APPLY never authorizes itself

When the operator is separately owner-approved for installation as a
root-owned reviewed executable, its default invocation is read-only.
APPLY also rejects execution from the untrusted checkout or any path except
the fixed root-owned, regular one-link mode 0755 operator at
`/usr/local/sbin/simple-deploy-executor-upgrade-933`. A separate installer
must prove that executable's reviewed source identity before LIVE execution.
\`--check\` is an explicit alias for the same dry run; it never writes a stage,
touches the installed file, requests GitHub credentials, or mutates systemd.

It reads only the fixed candidate and destination **public Python source**
plus sanitized properties of exactly two fixed systemd units. These fixed
read-only \`systemctl show\` requests use a bounded output limit and timeout.
No journald, credential environment, Docker inspect, registry, Compose,
runtime process data, protected application config or remote HTTP is read.

A successful CHECK requires, in two matching observations:

- SIMPLE-DEPLOY timer: \`LoadState=loaded\`, \`UnitFileState=disabled\`,
  \`ActiveState=inactive\`, \`SubState=dead\`, \`Job=0\`,
  \`NeedDaemonReload=no\`.
- SIMPLE-DEPLOY service: \`LoadState=loaded\`, \`ActiveState=inactive\`,
  \`SubState=dead\`, \`MainPID=0\`, \`Job=0\`,
  \`NeedDaemonReload=no\`.
- Expected fixed root-owned public-file metadata, inode/source stability and
  SHA-256/Git-blob identities, with no existing fixed stage.

On an idle host, `systemctl show` can emit `Job=` (an explicitly present
empty value) instead of `Job=0`. The operator accepts **only** those two
forms as no pending job. A missing `Job` property, nonzero job or unexpected
value still blocks; `unit_properties` continues to require every requested
field. This does not relax the timer's **disabled/inactive** requirement,
authorize service lifecycle changes or permit the one-file APPLY.

The already-staged root-owned #933 operator remains pinned to its original
Git blob until a **separate owner-authorized LIVE file replacement** installs
this corrected source. Merging a source-only fix does not modify the staged
operator, candidate, installed executor, systemd state or production runtime.

At issue discovery the timer was enabled/active, and the service was failed.
Those states **block CHECK and APPLY**, as designed. Disabling the timer,
quiescing/resetting the service or providing the source candidate are **not
actions of this operator** and need independent authorization. This operator
does not implicitly invoke \`systemctl stop\`, \`disable\`, \`reset-failed\`,
\`daemon-reload\`, \`restart\` or enable the timer.

A command-line \`--apply\` switch is **not owner authorization**. APPLY also
requires root, the same successful preflight and a separately owner-approved
root-owned, one-link **0400** proof file at the fixed \`/run\` path. Its exact
JSON is:

\`\`\`json
{
  "schema": "rpi5.simple_deploy_executor_upgrade_owner_authorization.v1",
  "issue": 933,
  "commit": "c0861f8fb4c8ea1df73fcffc340323d7d846641a",
  "git_blob_sha1": "8ef118030c8c83b8b713d93a80d5710fa6f79f3c",
  "source_sha256": "ed906786fd85169c6c555a3ac466b157edaf24a65fe12f60ee2ec6940ade20d0",
  "baseline_sha256": "bec054249e6729f6a5a87516758fda77d5382d5b18c37318ec7b953d36422af2",
  "target": "simple_deploy_v1.py",
  "operation": "single_atomic_replace",
  "no_automatic_retry_rollback_cleanup": true
}
\`\`\`

The proof is **only a local guard**. It is not cryptographic proof of the
owner's identity and it is never created by the operator. The independently
verifiable owner LIVE authorization and the exact trusted materialization
of this file must be established *before* APPLY by a separately reviewed
workflow; a local root process must not manufacture LIVE authority.
If the owner-proof provenance is not independently established, **STOP**.

## Future owner-gated one-file transaction

After first and second preflight, the operator checks the exact root-owned
proof, then runs another two-observation preflight to reject drift. APPLY
performs only these bounded effects:

1. Exclusive same-directory creation of a single fixed-named stage file with
   \`O_EXCL|O_NOFOLLOW\` and 0600 initial permissions. This is the **first
   mutation** and consumes the separately frozen LIVE authorization.
2. Write exactly the reviewed source bytes, set root:root/0444, \`fsync\`,
   reopen and verify source SHA-256 and Git blob identity.
3. Re-check both fixed systemd units for disabled/inactive quiescence; reopen
   and compare the exact original installed inode, mtime, length and hash.
   If a service lifecycle event or file race is observable, **STOP**.
4. One atomic same-directory \`os.replace\` of the stage over precisely
   \`simple_deploy_v1.py\`, followed by directory \`fsync\`, root/0444
   verification and another sanitized quiescence check.

No CV receipt, state, image, registry, Compose file, checkout or unrelated
path is touched. Nothing starts the service or timer. There is no retry,
automatic cleanup or rollback. If an error happens after stage creation, the
stage (or final file, if already replaced) is left as evidence; the operator
must not be called again until separately reviewed and owner-authorized
recovery. A root-owned directory does not eliminate an external administrator
starting a service between status sampling and replacement: this narrow
race remains a LIVE precondition. The owner must independently establish
exclusive quiescence for the entire mutation window; otherwise APPLY is
**BLOCKED**, even if CHECK passes.

## Fault-injection and future LIVE gate

\`python3 tests/test-simple-deploy-executor-upgrade-933.py\` covers read-only
CHECK, missing/stale/changed source, Git-blob mismatch, symlinks, permissions,
stale installed baseline, existing stage, timer enabled/active, service
active/failed, systemd job contention, changed observations, owner-proof
mismatch, non-root apply, successful same-directory replacement, race-before-
replace, simulated rename error after staging, and no implicit mutation
primitives. \`make validate\` includes the test.

**Separate future decision:** after source PR is reviewed and the current
installed baseline is revalidated, request a new bounded STRICT owner
authorization for only the exact root candidate/approval preparation,
operator installation if needed, explicit timer/service quiescence,
one single-file replace, and sanitized postverification. Such an authorization
must name the actual current GitHub commit, expected two SHA-256 values,
exact host and approved mutation classes. If any preflight is not provable,
do not run APPLY. There is no source-issue authority to merge or deploy.
