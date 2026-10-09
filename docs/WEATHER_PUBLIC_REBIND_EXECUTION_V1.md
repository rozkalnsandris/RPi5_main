# Weather PUBLIC — source-only rebind execution contract v1

Issue: `RPi5_main#915`. Roadmap: `#60`.
Machine contract: `ops/contracts/weather-public-rebind-execution-v1.json`.
Source-only evidence classifier: `scripts/weather_public_rebind_contract_v1.py`.
Tests: `tests/test-weather-public-rebind-execution-contract-v1.py`.

**Review state: source contract, not an installed host executor.** No write-capable
runtime wrapper is added. The source classifier accepts only pre-sanitized
evidence and cannot read the host or change anything. Future LIVE execution
requires a separately reviewed trusted executor or equivalent bounded
operator, plus exact owner LIVE authorization; merging this contract
grants neither.

## Observed vs target state

The 2026-10-08 authorized read-only RPi5 observation found the healthy
single Weather container with `wildcard` Docker publish, unchanged
`weather_data` volume, installed identity
`a74058dd735013e1b3dd450f9261b3f607c05e62`, clean host checkout
`fe69b6e325fa9edec04e8963b5010f946ac4d83c` and old installed
Compose hash `321fe0aa400d1a01e419f313a6c99ada311058496f36fed032daf1ac036fa16d`.
A later, separately authorized **read-only** host preflight observed installed
registry SHA-256 `88c3acbf304ab9676a6a767e5f3055351f20fd88ca9bf1bf4a2cb1210ef3617f`.
It is an exact byte-hash match to the historical `RPi5_main` registry
at `fe69b6e325fa9edec04e8963b5010f946ac4d83c`. The installed
SIMPLE-DEPLOY **identity file still names** the earlier
`a74058dd735013e1b3dd450f9261b3f607c05e62`; these sources
are intentionally recorded separately rather than treating the installed
file set as one coherent release. The previous candidate whole-registry
hash `e68fb9d674dbc044454563c8c8ba74c757c958ea78ff980dd0003b64d7e7bd7d`
was inferred from identity and **does not match** installed bytes.
Any subsequent host preflight must measure the actual installed registry
again and reject changes since this observation.

The reviewed RPi source at
`9f28ba941b9c4055f531d172cbf87f7a6d089b13` has Compose hash
`eddbe28efd5270c350adcf18413839ed80d27d95387473cf7f4e2bf68584a04c`
and registry hash
`91a2fe2d86d9da9ac4ee7a5031eea7a405d3d42faec24ed089b08534c7ac0f23`.
From the verified registry source at `fe69b6...` to reviewed source,
**only Weather's Compose file SHA-256 differs**. Weather shared-workflow
revision is already `297f554519849ab8dcaadc5517e60b8269a6efaa`
in the installed registry source; all four non-Weather target entries
remain identical. The operator therefore rejects even a Weather
shared-workflow revision change in this remediation. The current Weather consumer merge
is `0eba9d70bd5ee3e6f990a7e34a3b47fd3da93ebe`.

## Frozen phases — not runtime authorization

1. **Exact checkout gate:** require a newly owner-approved merged
   `RPi5_main/main` SHA, canonical clean checkout and, only with its
   own LIVE authorization, fixed `git fetch --no-tags origin main` plus
   `git merge --ff-only`; never reset/rebase/clean/force.
2. **Sanitized preflight:** verify the host installed identity, whole
   registry and Compose hashes and root metadata; verify only the
   Weather registry delta and one existing healthy Weather container.
   Check named volume identity, exclusive target lock, no prior blocked
   reconciler error, and immutable SHA-256 image digest equality across
   existing receipt, override and running container. Validate image
   metadata/revision/shared-workflow allowlist and the fixed private-home
   env file **only by permitted metadata**: `root:rozkalns-simple-deployer`,
   mode `0640` (read-only observation on 2026-10-08, consistent with
   private-home access separation). Never read or emit file content;
   unknown/baseline mismatch is BLOCKED before mutation.
3. **Three fixed file replacements:** only after explicit owner LIVE
   approval, under the *same* Weather reconciler lock, stage root-owned
   `0444` replacements using exclusive no-follow creation/fsync.
   Atomically replace reviewed Weather host Compose, the static registry
   (non-Weather targets unchanged), and exact-merged-SHA identity,
   with old-hash recheck immediately before replacement and post-hash
   verification. No generic install path or other host mutation.
4. **Forced recreate:** the normal SIMPLE-DEPLOY reconciler may return
   `NO_OP_CURRENT` if the image digest is unchanged, leaving wildcard
   publish untouched. Therefore use exactly the machine contract's
   Weather-only `docker compose up --force-recreate --no-deps --pull never`
   argument vector with the **existing** immutable digest-pinned
   override. This must not pull a new image, touch other services,
   recreate volumes or expose the existing protected env-file contents.
5. **Postverification:** require preserved image digest and volume,
   healthy container, loopback Docker publish **and** listener, liveness
   and readiness, public anonymous HTTP/connector evidence and no new
   unrelated ingress drift. Phase 7 must produce a fresh PASS under its
   separate GET-only authorization and exact-installed Cloudflare
   operator release; operator upgrade is not part of this Weather scope.

## Failure / recovery boundary

Before mutation: BLOCKED, no change. After the **first staging or
replacement mutation**: STOP on any error, timeout, unexpected head,
drift, Docker failure or unclear result. Preserve partial-state
evidence sanitized to stage/result/hash/class/health only.
**No automatic retry, rollback, cleanup, Compose down, volume deletion,
image pull, systemd, Cloudflare, credentials or DB writes.**
Any partial-state repair requires a separately reviewed recovery plan
and explicit fresh owner authorization.

This is a source-level specification and testable classifier; it is
**not yet a deployable live executor**. A later implementation must
prove the complete trusted execution state machine before the owner
is asked to authorize a Weather LIVE rebind.


## Reviewed Weather-only operator implementation

The new source script scripts/weather_public_rebind_operator_v1.py is a narrowly bound future host executor. It is NOT installed or invoked by this source change. Its default preflight does not create a lock; it requires the existing fixed Weather target lock. An apply run also requires the exact --expected-main SHA and the fixed --confirm REBIND-WEATHER-PUBLIC-915 token; these arguments are procedural safeguards, NOT owner LIVE authority.

Under a separately granted LIVE gate, the operator checks a clean canonical main checkout, exactly three installed root-owned 0444 files, the historical registry baseline, unchanged other targets, immutable image digest receipt/override/running identity, image metadata, and only metadata for the protected env file. It stages and replaces exactly the three fixed files with identity last, under the same held target lock. It then executes one reviewed Weather-only Compose force-recreate with --no-deps, --pull never and --wait, preserving the named data volume and image identity. Errors after any staging begin STOP without automated cleanup/rollback/retry. A local success returns LOCAL_PASS_PHASE7_PENDING, not Phase 7 PASS. Separate owner-authorized public HTTP and GET-only Phase 7 auditing is still necessary.

Tests: tests/test-weather-public-rebind-operator-v1.py. No LIVE, merge, host checkout sync, installation, service lifecycle or production mutation is performed by the source PR.


## Weather ingest and reconciler quiescence gate (#915)

The 2026-10-08 separately authorized, metadata-only observation found
`rozkalns-weather-public-ingest.service` in **failed/exit-code** state,
while `rozkalns-weather-public-ingest.timer` and
`rozkalns-simple-deployer.timer` were active/enabled. The generic
`rozkalns-simple-deployer.service` state was not established in that
observation. These are point-in-time findings and are **not** permission
to intervene in systemd.

The source operator now uses fixed, **read-only** `systemctl show`
queries returning only `ActiveState`, `SubState`, `Result` and
`UnitFileState` for exactly four allowlisted units:

- Weather ingest oneshot: `inactive/dead`, `Result=success`,
  `UnitFileState=static`.
- Weather ingest timer: `inactive/dead`, `Result=success`,
  `UnitFileState=enabled`.
- SIMPLE-DEPLOY oneshot: `inactive/dead`, `Result=success`,
  `UnitFileState=static`.
- SIMPLE-DEPLOY timer: `inactive/dead`, `Result=success`,
  `UnitFileState=enabled`.

Missing, failed, active, unknown, disabled, changed unit identities or
extra metadata **fail closed before any mutation**. The operator holds the
existing Weather target lock and rechecks quiescence immediately before
staging, after staging but before replacement, before **each** fixed-file
replacement, immediately before Docker forced recreate and after local
verification. A quiescence change after staging begins produces **STOP**,
without cleanup, retry or rollback.

**Recovery boundary:** a failed ingest service must be diagnosed and
resolved separately under explicit owner authorization. In particular
`systemctl reset-failed`, stopping/restarting the failed ingest service,
or stopping/starting/enabling/disabling either timer is **not** in this
source or future Weather rebind operator's authority. The earlier
private-home cutover performed narrowly authorized timer operations;
that historical authorization does not apply here. Likewise, a
running/persistent timer may trigger new work between observations,
so a fresh quiescence reading must accompany any later exact-head LIVE
decision. Simply marking a timer `disabled` or ignoring a retained
failure result is not an acceptable shortcut.

The host checkout still requires a separately authorized exact-source
fast-forward before the operator can pass its source gate. Merge of
this change does not deploy or execute the operator, restart services,
close Phase 7 DRIFT, or grant any LIVE/systemd/data permission.

## Git index ownership safety for root-run preflight (#936)

The reviewed Weather rebind operator's fixed `git()` source-gate helper
uses Git's global `--no-optional-locks` flag before `-c safe.directory`
and `-C`, including its `git status --porcelain=v1 --untracked-files=all`
clean-checkout check. Git documents that `status` may otherwise refresh and
rewrite the shared `.git/index` as an optimization even during inspection.
Disabling optional locks avoids that incidental root-owned index rewrite;
it does **not** skip the dirty-tree, exact-main, origin or root identity gates,
and is not a blanket filesystem read-only guarantee.

The October 9 preflight uncovered a root-owned Git index after an operator
check; the single-file owner was separately restored to `andris` with explicit
LIVE authority. This GitHub source change **does not** fix or rerun host
operators, recreate containers, restart systemd timers or authorize LIVE.
The last observed Weather timers remained enabled/inactive pending a new
owner-gated continuation. Source merge still needs a separately authorized
exact-source host update before it can affect installed operations.
