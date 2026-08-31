# P9 Gate D target-evidence fail-fast repair

Status: **SOURCE ONLY / FAIL-CLOSED REPAIR / NO LIVE AUTHORIZATION**

Canonical continuity: `RPi5_main#191`.
Related Control diagnostics: `rozkalns-control-center#490`, `#491`.

## Incident boundary

On 2026-08-30 the owner authorized exactly one trusted-RPi5 Gate D Control post-canary baseline collection for Control source:

`f9b900a884bffda993197fc7fa9223c886e11a90`

The one-shot operator stopped fail-closed with the sanitized error:

`P9_CONTROL_BASELINE=STOP reason=ControlPostCanaryProducerError:Control post-canary observation failed reviewed checks: ['target_pr_merge_evidence_exact']`

That LIVE authorization is consumed. The failed attempt is **not retryable** under the consumed authorization.

Source-order analysis proves:

- source-App/GitHub evidence collection was reached;
- both fixed D1 SELECT paths were reached and passed their existing zero-write metadata checks, because `d1_select_only_zero_write` was not among the failed producer checks;
- baseline evidence publication did not begin, because producer semantic validation failed before the atomic publisher opened/wrote its target;
- genuine P9 execution and StateStore mutation were not part of the baseline operator path.

No credential bytes or token secret belong in this document or any GitHub evidence.

## Failure class

Two source defects made this failure less safe and less diagnosable than intended.

First, `p9_control_postcanary_producer.py` represented the target PR merge-evidence contract as one aggregate boolean. The contract already required all of these predicates:

1. exact PR number;
2. `state == closed`;
3. non-empty `merged_at` string;
4. `draft == false`;
5. exact head SHA;
6. exact head repository full name;
7. base branch `main` plus exact base repository full name;
8. exact merge commit SHA.

The repair must preserve every predicate. It may improve only the sanitized diagnostic granularity.

Second, the baseline CLI constructed `FixedD1ReadClient(api_token=read_fixed_d1_token())` before `collect_control_postcanary_observation()` validated target GitHub semantics. Inside the collector, target issue/PR/merge/compare objects were fetched before D1, but their semantic predicates were evaluated only later by the producer after both D1 SELECTs. Therefore a public target-evidence mismatch could consume protected D1 capability before the mismatch was rejected.

## Repaired trust boundary

The repaired source introduces one typed `ControlPostCanaryTargetEvidence` value and one shared semantic failure-code path. The producer and collector use the same predicate implementation; the producer retains the final defense-in-depth checks and the existing evidence schema keys.

Target PR failures are sanitized into the same predicate classes already proven in Control #491:

- `TARGET_PR_NUMBER_MISMATCH`
- `TARGET_PR_NOT_CLOSED`
- `TARGET_PR_MERGED_AT_INVALID`
- `TARGET_PR_DRAFT_INVALID`
- `TARGET_PR_HEAD_MISMATCH`
- `TARGET_PR_HEAD_REPO_MISMATCH`
- `TARGET_PR_BASE_MISMATCH`
- `TARGET_PR_MERGE_SHA_MISMATCH`

The target issue, merge-parent and main/merge-base predicates also receive bounded metadata-only failure codes. No raw provider response body, credential, token, SQL row content or other secret-bearing data is included in those diagnostics.

The collection order becomes:

1. validate requested Control source SHA syntax;
2. verify exact Control source repository/main/CI evidence;
3. fetch the pinned historical canary run/jobs;
4. fetch and identify the fixed public target repository;
5. fetch the pinned target issue, PR, merge commit and merge-to-main compare;
6. validate **all reviewed target issue/PR/merge/compare semantics**;
7. only after step 6 passes, read the fixed D1 credential and construct the capability-specific D1 reader;
8. execute exactly the existing two source-fixed SELECT operations;
9. require the existing zero-write D1 metadata contract;
10. build the same bounded baseline evidence;
11. publish the same fixed evidence file atomically.

A target semantic failure therefore happens before the D1 credential read and before either D1 request.

## D1 contract remains unchanged

This repair does not change the D1 capability or SQL:

- account: `70e29dbca0e8363358659102d2b74178`;
- database: `8504e986-faf0-450c-bfb5-41b5dbf8be09`;
- credential path: `/root/.config/rozkalns-deploy-executor-p9/control-d1-read-token`;
- exactly the two existing source-fixed `SELECT` statements;
- response must still prove `changed_db=false`, `rows_written=0`, and `changes=0`.

No D1 write, migration, apply, generic SQL input or new credential source is added.

## Regression proof

`tests/test-deploy-executor-p9-control-baseline-failfast.py` must prove at least:

- every reviewed target issue mismatch stops before the D1 client factory;
- every existing target PR predicate mismatch returns its bounded sanitized diagnostic and stops before D1;
- merge commit/parent mismatch stops before D1;
- merge-to-main compare/merge-base mismatch stops before D1;
- the production default path does not call `read_fixed_d1_token()` or construct `FixedD1ReadClient` for those failures;
- a valid target evidence set constructs one D1 client and performs exactly the two existing SELECT calls in order;
- the baseline CLI contains no eager D1 credential read/client construction;
- no target PR predicate is removed or weakened.

Python `unittest.mock` call assertions are appropriate here because the security property is absence of a capability invocation, not merely a returned status.

## Reviewed host-upgrade source path

Merging repaired Python source does not change the installed trusted-RPi5 runtime.

`scripts/install-deploy-executor-p9-gate-d-failfast-upgrade.py` is a separate source-only, owner-gated three-target upgrade operator for a later LIVE decision. Its reviewed pre-state is fixed to the currently installed/source-matched Git blobs:

- producer old blob: `e534d97016cb43a3129cb6711527fdcea3cb178b`;
- collector old blob: `d61d2c992da709833425e82da1242b172e3cc5c1`;
- baseline CLI old blob: `4c406248875cd37963027f5b6fb950749ac5ad1e`.

Without `--apply`, the operator performs preflight only and reports `P9_GATE_D_FAILFAST_MUTATION=NO`. Source merge never authorizes `--apply`.

A future `--apply` requires a separate exact owner LIVE authorization bound to the merged/reviewed source SHA and the three fixed installed targets. The operator has no network, credential, D1, baseline collection, P9, StateStore, systemd or registry execution path and provides no retry or rollback path.

## Gates after source repair

This source repair may proceed through branch, tests, Draft PR, CI/review and Ready under FAST-LANE. It must STOP before merge.

Even after an explicitly authorized merge:

1. host installation of the repaired three files remains a separate LIVE gate;
2. the consumed failed Gate D authorization is not revived;
3. after repaired-host provenance is freshly proven, any new Gate D baseline collection requires a **new exact STRICT LIVE authorization**;
4. genuine P9 remains downstream and separately unauthorized.

No dummy READY, LIVE-AUTH, baseline evidence, authorization record or production mutation may be manufactured to exercise this repair.
