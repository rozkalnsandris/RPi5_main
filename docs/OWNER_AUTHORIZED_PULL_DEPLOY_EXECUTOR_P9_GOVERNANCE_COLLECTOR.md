# Owner-authorized deploy executor v1 — P9 governance writer-surface collector

Status: **SOURCE ONLY / DORMANT / NOT INSTALLED**
Roadmap: `RPi5_main#236`
Source gate: `RPi5_main#259`

This gate freezes the fail-closed input boundary for constructing the complete `GovernanceWriterSurfaceObservation` consumed by the already-merged P9 evidence producer. It does not install a collector, add credentials, read protected host state, change repository settings, enable the executor registry, create READY/LIVE-AUTH state, or authorize a P9 canary.

## 1. Why this gate exists

P0/P7 require the owner-authorization Issues surface to remain a reviewed trust root. An owner-created LIVE-AUTH issue can be trusted only while every actor/path capable of mutating that issue surface is either known and approved or causes governance to fail closed.

`p9_producer.py` already refuses `trusted=true` governance evidence while `APPROVED_GOVERNANCE_WRITER_SET_SHA256` is unset. This collector gate does not weaken that control. It only defines how a later root-owned collector must construct the complete typed observation from independently gathered source/runtime facts.

## 2. Exact authorization-repository source pin

The collector is pinned to the freshly reviewed authorization repository source:

- repository: `rozkalnsandris/ops-workflows`;
- repository id: `1328835922`;
- owner numeric id: `277435981`;
- owner type: `User`;
- source commit: `c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8`;
- root tree: `9649c6c38b4bce83ee535557dc7e8e335f8c08ad`.

The seven workflow blobs are also pinned individually. A later `ops-workflows` source change therefore fails closed until this RPi5 source contract is reviewed again.

The collector does not trust a caller-supplied tree-complete flag by itself. It reconstructs every Git blob SHA and recursively reconstructs the Git root-tree SHA from the supplied complete tracked-blob snapshot. The computed tree must equal both the observed tree and the source-pinned tree. Duplicate paths, unsupported modes, path traversal, file/directory conflicts, non-UTF-8 blobs, workflow inventory drift, or workflow blob drift are rejected.

The current `ops-workflows` repository is source-only/text-only for this contract. A future uninspectable binary/submodule surface is intentionally a review event rather than silently excluded from the writer audit.

## 3. Source-controlled workflow/token mutation surfaces

The source scanner inspects executable GitHub-side paths under:

- `.github/workflows/`;
- `.github/actions/`;
- `scripts/`.

Every workflow must have one explicit top-level `permissions` declaration. Missing, dynamic, or unsupported top-level permissions fail closed.

The scanner records a workflow writer identity when any workflow contains:

- `issues: write` at any permission scope; or
- `permissions: write-all`.

The scanner also records a token-source identity for source containing an Issues mutation surface such as `gh issue create/edit/comment/close/...`, direct repository Issues REST paths, or the corresponding common GraphQL mutation names.

This is intentionally conservative. A newly added executable path or source change changes the pinned Git tree and therefore requires source review before it can be accepted by the collector.

Fresh review of exact `ops-workflows/main=c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8` found seven workflows. Every one explicitly declares read-only permissions: `contents: read`, with issue-triggered lint jobs adding only `issues: read`. No current workflow was accepted from a search-index inference; each workflow source was read directly.

## 4. Human/team writer surface

The human surface uses typed collaborator observations with stable numeric GitHub user ids and normalized effective repository permission. Only `push`/`write`, `maintain`, or `admin` access becomes a writer identity. Read/triage access is not a writer.

The collector requires:

- a complete collaborator observation;
- the exact reviewed provenance id `github-rest.repository-collaborators.v1`;
- the authorization repository owner numeric id to be present;
- no duplicate identities or unknown permission values.

Current GitHub REST documentation states that `GET /repos/{owner}/{repo}/collaborators` is available to GitHub App installation tokens with Metadata read. This source gate does not create or expand any credential.

The authorization repository is user-owned, not organization-owned. Therefore the team surface is explicitly complete only when empty, with provenance `github-repository-owner-user-no-teams.v1`. If repository ownership/topology changes, collection fails closed and requires source review.

## 5. Installed App/integration surface remains an explicit capability boundary

The collector has a separate typed installed-App/integration surface. Each entry has:

- integration type (`github-app`, `oauth-app`, or another reviewed integration class);
- stable numeric integration id;
- canonical slug/name;
- normalized Issues permission (`none`, `read`, or `write`).

Only integrations with Issues write authority become writer identities. Unknown types, unknown permission values, duplicates, an incomplete observation, or wrong provenance are rejected.

The required provenance id is `github-admin.repository-installed-apps-integrations.v1`.

**This source gate does not claim that the currently installed Deploy Executor credential can produce that complete administration/integration inventory.** It deliberately models the capability as required-but-not-yet-installed. If the complete App/integration surface cannot be obtained with an already reviewed read-only capability, the next step must STOP for a separate architecture/credential/permission decision. A partial integration inventory must never be treated as complete.

## 6. Writer-set digest remains unapproved

A successful collector result is only a complete normalized `GovernanceWriterSurfaceObservation`. The existing producer then computes the deterministic writer-set SHA256.

`APPROVED_GOVERNANCE_WRITER_SET_SHA256` remains `None` in this gate. Therefore even a synthetically complete test observation cannot emit production `trusted=true` governance evidence without a later reviewed source change that pins a digest produced from a real complete audit.

The intended sequence is:

1. merge this source contract;
2. separately resolve and review the exact runtime capability that can establish every required writer surface;
3. under an appropriate owner gate, collect sanitized complete evidence without exposing secrets;
4. review the normalized writer set and exact collector/source identities;
5. separately source-pin the approved SHA256;
6. only then may the governance producer emit `trusted=true` for an unchanged fresh writer surface.

## 7. Source-only regression coverage

`tests/test-deploy-executor-p9-governance-collector.py` covers:

- known Git blob/tree hashing semantics;
- exact source commit/tree pinning;
- incomplete/tampered tree rejection;
- non-UTF-8/uninspectable source rejection;
- mandatory explicit workflow permissions;
- job-level `issues: write` detection;
- `write-all` detection;
- issue-mutation source detection;
- collaborator completeness and owner-presence requirements;
- user-owned empty-team invariant;
- installed App/integration completeness;
- unknown integration type/permission rejection;
- distinct GitHub App/OAuth/integration writer identities;
- direct compatibility with the existing deterministic producer writer-set digest.

The suite is intended to run in normal `make validate`, and the new module is covered by the existing deploy-executor `py_compile` wildcard.

## 8. Explicit exclusions

This gate does not authorize or perform:

- GitHub credential/PAT/private-key creation or placement;
- GitHub App permission/install/repository-scope changes;
- repository settings or Actions settings mutation;
- protected host inspection;
- collector/producer/spool/service installation or execution;
- production registry activation;
- P8 poller/dispatcher/systemd mutation;
- READY or LIVE-AUTH creation/change;
- `adapter.apply()`, authorization consumption, root helper, or result writer;
- production deployment, DB, Cloudflare, network, storage, Docker, or runner mutation.

Merge remains separately owner-authorized. Any later credential/admin API capability or host collector installation remains a separate owner-gated boundary.