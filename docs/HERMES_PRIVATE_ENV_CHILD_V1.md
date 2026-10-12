# Hermes private env child — #984

Status: **SOURCE PREPARATION / NOT LIVE READY**. This operator is an explicit,
create-only proposal for the child access decision left open by v4. Neither this
source change nor a merge authorizes protected reads or host changes.

## Why this is the next bounded outcome

The household API adapter from #975 already supplies the two public UI settings.
The separate owner-authorized metadata observation on 2026-10-11, against
`RPi5_main@4b64d30504bf51fe0ef6f78dd6ace40983ec390d`, classified the fixed private
child as absent. Parent metadata, local runtime-group exclusivity and the bounded
service-identity check matched. Consumer DAC was NOT_RUN; Compose access was
NOT_PROVEN. This is dated evidence, not a reusable authorization or today's host
baseline. The observation did not inspect state trees, protected contents or Docker.

The consumer's [Web architecture](https://github.com/rozkalnsandris/hermes-deals/blob/1b72efc5f43bbaae9c01bbe05e9bdd4ba2c1efb1/docs/WEB_ARCHITECTURE.md)
remains FastAPI/PostgreSQL/Jinja/HTMX/plain CSS. Its 2026-10-11 checkpoint's next
RPi5 configuration step is completed in source by #975; the checkpoint and
[rollout plan](https://github.com/rozkalnsandris/hermes-deals/blob/1b72efc5f43bbaae9c01bbe05e9bdd4ba2c1efb1/docs/plan/ROLLOUT_PREFLIGHT.md)
do not establish current production readiness. Consumer main at that reference
contains cleanup/progress changes after the reviewed UI/configuration release;
this does not replace the rollout plan's accepted immutable image candidate.

This outcome creates only the env child. Data/config-tree materialization has a
different protected-data scope and an unobserved baseline; it is not silently
combined with the file permission decision. V1-v4 scripts/contracts stay unchanged.

## Exact behavior

Entrypoint: `scripts/create-hermes-private-env.py`. Machine contract:
`ops/contracts/hermes-private-env-child-v1.json`.

The only arguments are `--expected-source-sha` and optional `--apply`. The SHA must
match the clean checkout, configured origin and reviewed bytes of this operator,
its contract and the imported v1-v4 source/contract chain. Git checks use v3's
non-writing validation. Run reviewed Python source with `-I -B` from a trusted,
root-owned checkout whose ancestors and source files cannot be changed by other
users. This is a required launch prerequisite, not something imports can establish
retroactively. Never run root Python from an untrusted caller-owned checkout.

Default execution observes metadata only. It requires root for the fixed private
metadata, rejects any existing target or staging path, and never opens `.env`
contents. It emits `ABSENT_METADATA_ONLY`, not readiness. Default execution also
requires separately authorized runtime metadata inspection.

Apply additionally:

1. Verifies installed service identity through exactly LoadState/User/Group/
   SupplementaryGroups/DynamicUser, and local NSS runtime-group exclusivity.
   Expected user/group is `rozkalns-simple-deployer`, supplementary group `docker`,
   DynamicUser=no. No group/user changes occur.
2. Opens every path component using directory descriptors and NOFOLLOW. Requires
   root-owned, non-group/world-writable destination ancestors and the existing
   root/runtime-group `0750` parent. Rejects POSIX access/default ACLs and symlinks.
   Locks the existing directory inode without creating a lock file. This serializes
   this operator, not unrelated privileged writers; concurrent administration must
   be excluded from the operation window.
3. Reads at most 64 KiB from the passwd-resolved `andris` home's fixed
   `hermes-deals/.env`, requiring a regular single-link `0600` file owned by that
   account. Source ancestors may be root or that account, never group/world writable.
   The source account is trusted; descriptor and before/after fingerprint checks
   reject observed source replacement or change.
4. Reuses v3's parser/projection: POSTGRES_USER/PASSWORD/DB plus HTTP_USER_AGENT
   become exactly DATABASE_URL and HTTP_USER_AGENT. Unknown keys are not published.
   Database components must be URI-unreserved ASCII (`A-Z a-z 0-9 . _ ~ -`); ambiguous
   delimiters, percent escapes and unsupported quoting stop. No credential is
   transformed or rotated to get past a refusal. Public household settings stay
   in the static adapter.
5. Creates exactly `.hermes-deals-api.env.child-v1.staged` with O_EXCL at `0600`,
   writes/fsyncs, revalidates source/identity/path metadata, then sets only this new
   inode to root/runtime-group `0640`. Publishes `hermes-deals-api.env` using Linux
   `renameat2(RENAME_NOREPLACE)` and fsyncs the parent. No overwrite or fallback
   rename is allowed. The existing parent is never chowned/chmodded/replaced.
6. Checks final inode metadata and performs an `os.access(R_OK)` check in a short
   child process under the observed service UID/GID and docker supplementary group.
   It reads no destination contents. This proves only DAC in that process, not
   Compose interpolation, systemd sandbox/MAC behavior, remote NSS completeness,
   connection validity or application readiness. Identity/path checks run again.

The fixed legacy env staging path must also be absent. Other private children are
not enumerated, opened or modified. There is no data/config-tree copy, DB access,
Docker/Compose call, installed registry/adapter change, service/timer operation,
network change, migration, adoption or activation. Core dumps are disabled in the
operator process. Protected values, secret-derived hashes, raw unit/NSS data and
exception text never appear in its receipt.

## Failure and later authorization

Receipt fields distinguish `protected_read_started`, `mutation_attempted` and
`published`. Mutation is marked before the O_EXCL attempt because an interruption
can leave its outcome uncertain. Error/timeout/interruption means STOP. A partial
stage or published child is deliberately preserved; there is no automatic retry,
cleanup, rollback, overwrite or fallback to v2/v3. A stage may remain `0600` or
`0640` depending on the failure point. Later inspection/recovery is a new exact
owner decision. A published file followed by failed verification is not success.

Before requesting LIVE, freeze the merged source SHA and reviewed trusted launch
location, verify exact-main CI, and prepare one operation envelope on `rpi5` covering
any necessary trusted-source placement, fixed metadata/NSS/unit observations, root
execution, the one bounded protected source read, creation/ownership/mode of the
one new child via its fixed stage, directory fsync and disposable-child DAC check.
No source checkout is installed by this PR. The preserved failed trusted checkout
must not be altered. The earlier metadata-only authorization cannot be reused.

Fresh mismatching metadata, existing child/stage, ambiguous URI syntax, unsupported
filesystem publication or changed source stops the operation without attempting an
alternate path. All outcomes force `activation_eligible=false` and
`compose_runtime_access=NOT_PROVEN`.

Even successful child creation leaves the state-tree baseline/materialization,
paired household registry/adapter adoption, isolated DB backup/restore proof,
bounded `0007 → 0008` migration, Nginx routing and exact-release UI acceptance
outstanding. An env-only partial prerequisite will not satisfy v4's combined
state-tree/child classification; do not treat that as permission to run v2/v3.
Hermes activation remains fleet-last, with no LIVE target selected by this source PR.

## Validation and references

`python3 tests/test-hermes-private-env-child.py` uses synthetic files and identities.
It covers two-key projection, no-content-read default, inode/path/ACL refusal,
source drift/size limits, publication collisions, partial failures and sanitized
receipts. It is registered in `make test`; existing v3/v4/household tests remain.
No test reads protected production configuration or calls live Docker/systemd.

Publication semantics: [Linux renameat2](https://manpages.debian.org/bookworm/manpages-dev/renameat2.2.en.html).
Descriptor, NOFOLLOW and access semantics: [Python os](https://docs.python.org/3/library/os.html).

**Production deploy/change REQUIRED for this source PR: NO.**
