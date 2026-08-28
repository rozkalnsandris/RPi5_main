# Owner-authorized deploy executor v1 — P9 read-only canary source preparation

Status: **P9 CORE MERGED — EVIDENCE/RUNTIME PREREQUISITES STILL SOURCE-ONLY**
Roadmap: `RPi5_main#236`

P8 is complete and accepted on RPi5 at reviewed source
`6a43ef875c785321a1b6bf09d8e558c5151c8546`: the dedicated unprivileged
poller is active on its timer, authenticated read-only polling succeeds, the
production operation registry remains empty/disabled, the dispatcher remains
mutation-disabled, and `PRODUCTION_MUTATION_STARTED=false`.

The P9 decision core from `RPi5_main#250` is merged on `RPi5_main/main` at
`d425f98db85fc2ffdffb2d66f6b34727e5e75b07`; exact-main Validate #612 and
policy checks passed. This does **not** make P9 live-ready. The next source gate
is `RPi5_main#251`, which freezes fail-closed JIT governance and sanitized
operation-baseline evidence contracts without adding a live entrypoint or host
read/mutation path.

P9 is a different gate from P8. It must use a genuine owner decision bound to a
genuine READY deployment queue item; source preparation must not create a dummy
`[LIVE-AUTH]`, turn a WAITING/BLOCKED queue READY, install a credential, change
systemd, widen GitHub App permissions, or execute a production adapter.

## P9 source goal

The merged pure read-only decision core can eventually produce `DRY_RUN_READY`
only after all authority/evidence gates pass. It adds no live entrypoint and
does not modify the P8 poller, systemd units, installed credentials, or the
production registry.

The future P9 invocation must compose the already-reviewed components rather
than replace them:

1. a fresh JIT writer-set governance attestation for the `ops-workflows` Issues
   authority surface;
2. the P1 LIVE-AUTH parser/owner/TTL/body-hash protocol;
3. the P2 authoritative read-only GitHub transport;
4. strict READY queue normalization and exact authorization/queue binding;
5. read-only source repository identity, merged/reachable exact SHA and
   exact-SHA successful CI evidence using the separate `Rozkalns Automation`
   read-only App trust domain;
6. an operation-specific read-only target baseline resolver;
7. static registry resolution and adapter `preflight()` only;
8. an immediate final governance freshness check and LIVE-AUTH unchanged-body
   re-fetch;
9. durable state transition to `ACCEPTED` and a sanitized local
   `DRY_RUN_READY` result.

The P9 core never calls `adapter.apply()`, `StateStore.consume()`, the dispatcher,
a root helper, Docker, systemd mutation, or a GitHub result writer.

## Two independent read-only GitHub identities

P9 must preserve the P0 trust separation:

- `Rozkalns Deploy Executor` remains installed only on
  `rozkalnsandris/ops-workflows` with Issues read-only plus Metadata and no
  GitHub write permission. It is the authorization reader.
- `Rozkalns Automation` remains the source/CI reader with Actions read +
  Contents read on only the existing reviewed source repository allowlist.

Do not widen Deploy Executor permissions merely to read source/CI, and do not
silently reuse or broaden the existing CV-only sudo token broker for P9.
Supplying the Automation App credential to the executor is a later host/
credential/systemd boundary and requires its own exact live authorization.

The source evidence allowlist is bound to stable repository IDs and workflows:

- `rozkalnsandris/RPi5_main` — `1323383044` — `validate.yml`
- `rozkalnsandris/hermes-tech` — `1323427708` — `ci.yml`
- `rozkalnsandris/rozkalns-cv` — `1325237749` — `ci.yml`
- `rozkalnsandris/hermes-deals` — `1317143994` — `ci.yml`

An authorized SHA may be older than current `main` if and only if GitHub proves
it is still an ancestor/merge base of current `main`; a later docs-only main
commit must not invalidate a previously merged exact source SHA. The exact SHA
still requires a successful completed main-branch workflow run and at least one
successful job.

## JIT writer-set governance is mandatory

`protocol.read_live_auth(..., governance_ok=True)` must never be reached by a
permanent configuration constant. A P9 caller must supply a short-lived,
reviewed JIT governance attestation bound to the exact `ops-workflows`
repository ID and a digest of the observed writer set.

The source core accepts the attestation only when:

- the repository name and numeric ID match the authorization repository;
- the attestation explicitly says the writer set is trusted;
- the writer-set digest is a canonical SHA-256 value;
- its observation time is no more than five minutes behind a fresh GitHub
  server clock and is not in the future.

The same attestation is checked against a second fresh GitHub server clock
immediately before the final LIVE-AUTH unchanged-body re-fetch. Any stale,
unknown or untrusted writer surface fails closed.

`RPi5_main#251` adds only the strict source parser/schema for this evidence. The
producer and placement/provenance mechanism remain a separate reviewed
source/host boundary: the unprivileged executor must not be able to mint its
own `trusted=true` attestation.

## Baseline resolver boundary

P9 cannot emit `DRY_RUN_READY` from queue/source/CI evidence alone. The selected
operation must also supply a read-only resolver for its exact expected target
baseline.

The dormant Hermes Deals canary names
`hermes-deals.origin-path-registration.v1`. `RPi5_main#251` freezes a sanitized
baseline evidence schema bound to the exact operation/target/source SHA and
explicit registration/probe/dispatcher/workflow/read-only assertions. It does
not authorize direct reads of the root-owned registration or other protected
runtime paths.

The future producer for that sanitized evidence must itself be narrowly
reviewed, source-identified and separately authorized for any protected host
inspection or file placement. Do not broaden poller permissions or create a
generic root-read/helper capability to bypass this gate.

## Source files in the merged core and evidence follow-up

Merged by `RPi5_main#250`:

- `ops/lib/deploy_executor/source_evidence.py` — stable source-repository
  identity, ancestor/reachability and exact-SHA CI proof over an injected
  read-only GitHub client.
- `ops/lib/deploy_executor/p9_canary.py` — dependency-injected P9 orchestration
  core with JIT governance, READY queue, source/CI, baseline and adapter
  preflight gates; output is local `DRY_RUN_READY` only.
- `tests/test-deploy-executor-p9-prep.py` — adversarial offline tests.

Prepared by `RPi5_main#251`:

- `ops/lib/deploy_executor/p9_evidence.py` — strict JIT governance and sanitized
  Hermes baseline evidence contracts;
- `tests/test-deploy-executor-p9-evidence.py` — adversarial schema/identity/
  freshness/source-binding tests;
- `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_EVIDENCE_CONTRACTS.md` —
  provenance and protected-host boundary.

No production operation is added to `ops/deploy/executor-operations.json`.
No systemd/service/poller/dispatcher source is changed by these source gates.

## Exit / later gates

The #251 evidence source gate is mergeable only when focused tests and normal
repository CI are green and review finds no new write/privilege path.

After #251 merge, P9 is **still not automatically live-ready**. Before a genuine
canary the remaining prerequisites must be freshly resolved:

- a real READY queue item and explicit owner decision, never a placeholder;
- a reviewed producer/provenance path for the short-lived writer-set governance
  attestation;
- a reviewed producer/provenance path for sanitized Hermes baseline evidence;
- source + separately authorized host wiring for the Automation App read-only
  credential/client if the current runtime lacks it;
- a one-shot P9 entrypoint that composes only the reviewed read-only pieces;
- fresh exact-main CI and cross-repository compatibility evidence.

Any credential placement, service/unit change, systemd reload/restart/enable,
protected host evidence inspection, GitHub permission change, or other live
mutation remains separately owner-gated. P10 production execution remains a
later independent LIVE STOP.
