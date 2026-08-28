# Owner-authorized deploy executor v1 — P9 evidence contracts

Status: **SOURCE CONTRACT ONLY — NO LIVE AUTHORIZATION / NO HOST MUTATION**
Roadmap: `RPi5_main#236`
Work item: `RPi5_main#251`

This gate follows the merged P9 decision core in `RPi5_main#250`. It freezes the
shape of two inputs that the future P9 one-shot runtime needs without granting
that runtime permission to inspect protected host configuration.

## Non-goals

This source change does not:

- create or edit a `[LIVE-AUTH]` issue;
- turn a deploy queue item `READY`;
- add an operation to the production executor registry;
- change the P8 poller, service, timer or dispatcher;
- install or expose either GitHub App credential;
- inspect `/etc`, `/root`, runner worktrees or other protected host state;
- call `adapter.apply()`, a root helper, Docker, systemd or a GitHub writer.

The production registry remains `execution_enabled=false` with `operations=[]`.

## JIT writer-set governance evidence

`ops/lib/deploy_executor/p9_evidence.py` accepts exactly one schema:

`rozkalns.deploy-executor-p9-governance-evidence.v1`

Required fields are exactly:

- `schema`;
- `repository` = `rozkalnsandris/ops-workflows`;
- `repository_id` = `1328835922`;
- `observed_at` = RFC3339 UTC timestamp ending in `Z`;
- `writer_set_sha256` = canonical lowercase SHA-256;
- `trusted` = literal `true`.

The observation must be no more than five minutes behind a fresh GitHub server
clock and must not be in the future. Missing, extra, stale, untrusted or
identity-drifted evidence fails closed.

This parser does **not** make an arbitrary local JSON file authoritative. The
future producer and placement/provenance mechanism must be separately reviewed
and must ensure the unprivileged executor cannot mint or modify its own trusted
writer-set attestation. No permanent `governance_ok=true` configuration is
permitted.

## Sanitized Hermes Deals baseline evidence

The first canary resolver remains:

`hermes-deals.origin-path-registration.v1`

Its source parser accepts exactly:

`rozkalns.deploy-executor-p9-hermes-origin-baseline.v1`

The evidence is bound to all of:

- operation `hermes-deals.origin-path-audit.v1`;
- source repository `rozkalnsandris/hermes-deals`;
- target alias `hermes-deals-origin-path-audit`;
- the exact 40-character source SHA authorized by LIVE-AUTH/queue binding;
- the exact expected resolver contract;
- an observation no more than five minutes old relative to a trusted server
  clock.

The sanitized producer must explicitly attest all of these booleans as `true`:

- `registration_identity_ok`;
- `registered_source_match`;
- `probe_identity_ok`;
- `dispatcher_identity_ok`;
- `workflow_identity_ok`;
- `mutation_surface_read_only`.

The parser returns only a local `BaselineEvidence` with a canonical SHA-256 ID
of the sanitized object. It does not expose protected configuration values.

## Protected-host provenance remains a separate gate

The existing Hermes Deals registration is root-owned/protected and the current
legacy dispatcher has runner-worktree assumptions. The unprivileged deploy
executor must not receive broad read permission merely to satisfy P9.

A later source gate must define a narrow producer/consumer mechanism that:

1. checks the reviewed registration/probe/dispatcher/workflow identities inside
   an explicitly authorized protected boundary;
2. emits only the allowlisted sanitized fields above;
3. places the evidence so the executor can read but cannot forge/replace it;
4. binds producer source identity and freshness;
5. never grants a generic root-read or command-execution capability.

Designing or installing that producer is not authorized by this contract.

## Two GitHub App trust domains remain separate

The authorization reader remains `Rozkalns Deploy Executor`, installed only on
`ops-workflows` with Issues read-only plus Metadata. Source/CI verification
remains the separate `Rozkalns Automation` trust domain with Actions/Contents
read-only on the reviewed source allowlist.

Do not widen Deploy Executor permissions, install a new credential, or broaden
the CV-only token broker as a side effect of this source gate.

## Exit gate

This source contract is complete only when focused tests and normal repository
CI pass and review confirms that no new host read/write or mutation path was
introduced.

After merge, P9 is still not live-ready. Remaining prerequisites include the
reviewed attestation producers/provenance, separate Automation App runtime
credential/client wiring, a genuine READY queue item and genuine owner
LIVE-AUTH. Those are later gates. P10 remains separately owner-gated.
