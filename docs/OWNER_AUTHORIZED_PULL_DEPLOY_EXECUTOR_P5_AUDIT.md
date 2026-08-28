# Owner-authorized deploy executor v1 — P5 interface/security audit

Status: **P5 SOURCE ONLY — mutation disabled**
Roadmap: `RPi5_main#236`

This audit binds the P1–P4 executor contracts to the merged P3 authorization surface and to the first reviewed target, `rozkalnsandris/rozkalns-cv`. It authorizes no GitHub App creation or permission change, credential placement, host installation, sudo/systemd mutation, LIVE-AUTH creation, deployment, DB write, Cloudflare change, or other live mutation.

## Frozen source baselines

- `RPi5_main/main = 660099cb401a8692b66cdf11510a7c1eb368215a` (P4 merged/green baseline).
- `ops-workflows/main = c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8`.
- `rozkalns-cv/main = d25730b20c41edff29a83927bff386751f053cd0`.
- `ops-workflows` stable repository ID: `1328835922`.
- `rozkalns-cv` stable repository ID: `1325237749`.

The machine-readable copy is `ops/deploy/executor-interface-audit.json`.

## 1. LIVE-AUTH producer -> executor consumer

PASS at the source-contract layer.

`ops-workflows/policy/live-auth-v1.json` and `policy/schemas/live-auth-v1.schema.json` agree with `RPi5_main` P1 protocol on:

- canonical authorization repository and stable repository ID;
- owner numeric GitHub ID `277435981`;
- one open Issue, not PR;
- fixed 600-second server-time TTL and 30-second maximum future skew;
- exact LIVE-AUTH fields and strict unknown-field rejection;
- raw-body plus canonical-payload digest revalidation;
- exact queue/source/target/operation/baseline/mutation/rollback/exclusion/dependency binding;
- executor authorization credential read-only on Issues;
- receipt/reporting state being non-authoritative.

The P2 transport uses authoritative fresh GETs for LIVE-AUTH revalidation; conditional `304` is polling-only.

## 2. Queue -> static operation normalization

PASS at the source-contract layer.

P4 parses exactly one `## Queue contract`, requires an open `[DEPLOY-QUEUE][READY]` issue with one lowercase 40-character source SHA, and selects an operation only from exact static selectors. Queue prose is not command/path/argv/mutation authority. The complete queue contract is cryptographically bound into dependencies by `queue-contract-sha256:<digest>`.

The real production registry remains deliberately unchanged and empty:

```json
{
  "schema_version": 1,
  "execution_enabled": false,
  "operations": []
}
```

P5 proves the first target only with `tests/fixtures/deploy_executor/operations_cv_p5_audit.json`; that fixture is not a production registry.

## 3. Poller -> privileged dispatcher boundary

PASS as a narrow source contract; no privileged dispatcher is installed or enabled.

`dispatch_contract.py` permits only:

- authorization repository name and stable repository ID;
- authorization GitHub issue ID and issue number;
- request UUID.

It rejects extra fields, including source SHA, target alias, operation ID, command, path, argv, rollback command and mutation budget. The privileged side must therefore independently re-fetch LIVE-AUTH, queue/source/CI/baseline state and the source-controlled operation registry.

This preserves the P0 confused-deputy invariant: the unprivileged poller cannot tell the privileged side what to execute.

## 4. Proposed poller systemd security posture

`ops/systemd/rozkalns-deploy-executor.service` is source proposal only; it is not installed or enabled.

Required properties include:

- dedicated unprivileged `rozkalns-deploy-executor` user/group;
- `NoNewPrivileges=true`;
- no sudo command/path and no Docker socket;
- empty capability bounding and ambient capability sets;
- `ProtectSystem=strict`, `ProtectHome=true`, `PrivateDevices=true`;
- namespace, `/proc`, kernel and SUID/SGID restrictions;
- only `AF_UNIX`, `AF_INET`, `AF_INET6` address families;
- writable state limited to `/var/lib/rozkalns-deploy-executor`;
- `SystemCallFilter=@system-service`.

Local Debian systemd 257 check during P5:

```text
systemd-analyze security --offline=yes ops/systemd/rozkalns-deploy-executor.service
Overall exposure level: 1.5 OK
```

This result is source-review evidence only. P8 must rerun `systemd-analyze security` against the exact source proposed for installation and against the actual target host systemd version.

## 5. First target: rozkalns-cv

### Existing autonomous controller is NOT the executor adapter

The current installed/source controller `ops/bin/rozkalns-cv-pull-deploy` runs as `andris` and asks the CV preflight to resolve current `origin/main`. The target preflight likewise sets `TARGET_SHA` from `refs/remotes/origin/main`.

That is correct for the existing autonomous `AUTO_DEPLOY_SAFE` CV pull controller, but it is not acceptable as the owner-authorized executor adapter because the new path must begin from the independently revalidated LIVE-AUTH exact SHA. P5 therefore explicitly forbids using the existing controller itself as the universal adapter.

### Lower-level exact-SHA helper contract

The existing target helper `runner/release/rozkalns-cv-pull-deploy-main` is compatible with a future fixed exact-SHA adapter under these constraints:

- source blob: `c787789e77c31576310bed28da0fbc893cfabb5f`;
- installed path: `/usr/local/sbin/rozkalns-cv-pull-deploy-main`;
- installed owner/mode expected: `root:root:755`;
- deploy library source blob: `ade60abbfea3cf56b1a56bbc1b2e0669b1a1b983`;
- library installed path: `/usr/local/libexec/rozkalns-cv/rozkalns-cv-deploy-library`;
- helper requires invocation through the existing `andris` sudo boundary and validates caller identity;
- evidence directory is resolved from the validated sudo user's home as `<sudo-user-home>/.local/state/rozkalns-cv-pull-deploy/evidence`; no concrete user-home path is authority in the executor contract;
- helper accepts one exact target SHA and itself revalidates that SHA is current `origin/main` before mutation;
- helper produces transactional summary/evidence and verifies the public frontend contract.

The current installer writes a sudoers rule for exactly the fixed helper path. The future executor poller itself must never receive that sudo capability. Any later mutation-capable adapter/dispatcher must preserve a fixed, project-specific crossing and must not expose arbitrary commands/paths/argv.

### Rollback is a hard compatibility constraint

The CV deploy library automatically attempts rollback after a post-mutation failure before transaction commit. Therefore this helper is executor-eligible only with `rollback_policy=BUILTIN_TRANSACTIONAL_V1` in the static registry, normalized queue and LIVE-AUTH. `rollback_policy=NONE` is incompatible and must be rejected before mutation.

The P5 dormant adapter contract enforces this exact policy and a single `rozkalns-cv.transactional-release` mutation-budget unit.

### P5 adapter remains inert

`CvExactShaAdapter` provides the reviewed adapter ID and validates source/target/rollback/mutation/exclusion/helper-identity dependencies. Its `apply()` always fails with `mutation-disabled` in P5. It contains no process-launch, privilege escalation or generic execution bridge.

A future mutation-capable implementation is a new source change and a later explicit live gate; P5 does not authorize it.

## 6. Source/CI credential split

The future authorization reader and the existing source/CI reader remain separate capabilities:

- future authorization reader: `ops-workflows` only, Issues read-only, no writes;
- existing `Rozkalns Automation`: existing approved repository scope, Actions read + Contents read; no Issues/write expansion.

P5 requires source-repository identity, exact source SHA/current-main rule, exact-SHA CI and helper-source identity to be revalidated by the source/CI reader. No permission change is made here.

## 7. Result/evidence handoff

PASS at the source-contract layer.

Local durable evidence remains primary. GitHub receipts are non-authority, no GitHub receipt writer is enabled, and reporting failure must never replay execution. CV evidence paths remain target-specific and must not be copied into public GitHub issues if they contain protected runtime data.

## 8. P5 security outcome

The cross-repository source contracts are compatible only under the explicitly separated boundaries above:

1. READY queue is eligibility only.
2. LIVE-AUTH is separate owner authority.
3. poller sends identity only across privileged IPC.
4. privileged side independently revalidates authority and registry.
5. the existing autonomous CV controller is not used as the executor adapter.
6. the CV lower-level helper is bound by exact helper/library identities and `BUILTIN_TRANSACTIONAL_V1`.
7. the P5 CV adapter is dormant and cannot mutate.
8. the production registry remains empty and disabled.

P7 remains a separate LIVE trust-boundary gate. Before any App creation or authorization-surface enablement, P7 must freshly prove authorization-repository governance/writer scope and obtain separate owner authorization. P8 host installation, P9 genuine dry-run authorization and P10 production mutation remain separately blocked.
