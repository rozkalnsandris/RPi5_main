# P9 isolated LIVE-AUTH authorization surface

Status: SOURCE ONLY / DORMANT / NOT CREATED
Roadmap: `RPi5_main#236`
Canonical program: `docs/AUTOMATION_MASTER_PLAN.md`

## Decision

The owner selected `P9 TRUST DECISION: ISOLATED-AUTH-SURFACE` after the merged P9 governance collector proved that the current read-only Deploy Executor credential cannot independently enumerate the complete installed-App/integration writer surface of `ops-workflows`.

P9 therefore does **not** broaden the autonomous executor with repository Administration permission, a PAT, a user token, or any other admin credential. Instead, LIVE-AUTH authority moves to a separately owner-approved isolated repository while deployment eligibility remains in `rozkalnsandris/ops-workflows`.

This document and `ops/deploy/executor-p9-isolated-auth-surface.json` are source contracts only. They do not create a repository, change repository settings, change App installation scope or permissions, place credentials, alter P8/systemd, create LIVE-AUTH, or enable production mutation.

## Frozen repository roles

### Queue repository

`rozkalnsandris/ops-workflows` remains the canonical `DEPLOY-QUEUE` repository.

Queue state is eligibility evidence only. It is not owner execution authority. A queue mutation can never substitute for, create, or modify LIVE-AUTH authority.

Stable current queue repository ID: `1328835922`.

### Isolated authorization repository

The intended repository identity is:

`rozkalnsandris/deploy-authorizations`

It does not exist at this source gate. Its stable numeric GitHub repository ID is therefore intentionally **unbound**. The machine contract records `authorization_repository_id=null`, `activation_enabled=false`, `runtime_binding_ready=false`, `host_wiring_enabled=false`, and `production_mutation_enabled=false`.

A later source binding must use the actual GitHub-assigned stable repository ID after a separately authorized repository-creation/settings transaction. No synthetic ID, placeholder repository, temporary repository, or name-only trust is permitted.

## Required isolated-repository invariants

Before any P9 runtime binding can become Ready, the future repository must be proven to satisfy all of these conditions in one owner-authorized trust-boundary transaction:

- repository identity is exactly `rozkalnsandris/deploy-authorizations` plus its fresh stable numeric GitHub ID;
- visibility is private;
- Issues are enabled;
- GitHub Actions are disabled for the repository so no workflow can acquire `GITHUB_TOKEN` authority there;
- no unapproved human collaborator has access that can edit LIVE-AUTH Issues;
- no team writer surface exists for this user-owned repository;
- no unapproved GitHub App/OAuth/integration can edit Issues in the repository;
- the configured owner numeric identity remains `277435981`;
- any later change to collaborators, integrations, Actions enablement, repository visibility, or issue-write authority is a trust-boundary change that invalidates the accepted setup until separately reviewed.

GitHub documents that disabling Actions at repository level prevents workflows from running in that repository. The isolated design uses that product control to remove workflow `GITHUB_TOKEN` from the authorization writer surface instead of granting the executor Administration read solely to audit workflow settings.

## Approved writer/readers

The intended LIVE-AUTH writer set is deliberately narrow.

Owner authority:

- GitHub user ID `277435981`;
- `type=User` remains mandatory in LIVE-AUTH validation.

Approved owner-operated integration:

- GitHub App ID `1144995`;
- slug `chatgpt-codex-connector`;
- Issues write is permitted only as the explicitly owner-invoked operator path that creates a LIVE-AUTH after a separate owner command;
- unattended automation by that integration is not authorized by this contract.

Autonomous executor reader:

- `Rozkalns Deploy Executor` App ID `4748870`;
- Issues read-only;
- Metadata read-only/minimum;
- no GitHub write permission on the authorization surface;
- webhook disabled remains the target posture.

No other issue writer is approved by this source decision.

## Installation-token isolation

The queue repository and authorization repository are separate trust roles even if the same read-only Deploy Executor installation is later selected for both repositories.

Future runtime source must mint repository-scoped installation tokens per role rather than turning the current one-repository P8 token into an unnecessarily broad generic token:

- queue-read token: only `rozkalnsandris/ops-workflows`, Issues read;
- authorization-read token: only `rozkalnsandris/deploy-authorizations`, Issues read;
- no token may carry Issues write or repository Administration permission.

The current P8 source and installed runtime remain bound to `ops-workflows` only. This PR does not alter that installed configuration.

## Protocol migration contract

The current LIVE-AUTH v1 implementation intentionally conflates authorization repository and queue repository through the existing `AUTHORIZATION_REPOSITORY` constant. That behavior remains unchanged in this source-decision gate so current P8/P9 code cannot silently begin consuming a repository that does not yet exist.

After the future repository has been created and its stable ID has been reviewed, a separate source PR must split the roles explicitly:

1. `QUEUE_REPOSITORY` remains `rozkalnsandris/ops-workflows` with stable ID `1328835922`;
2. the LIVE-AUTH repository becomes `rozkalnsandris/deploy-authorizations` plus its real stable repository ID;
3. payload `queue_repository` validation continues to require `ops-workflows`;
4. issue acceptance validates the isolated repository name **and** stable numeric ID;
5. governance acceptance no longer depends on the broad `ops-workflows` writer-set digest as the LIVE-AUTH authority surface;
6. the isolated repository setup evidence becomes the trust-root prerequisite for LIVE-AUTH acceptance;
7. P8/poller/runtime client composition is updated only after that source migration is separately reviewed and merged.

Until those steps are complete, P9 remains mutation-disabled and no genuine LIVE-AUTH canary is eligible.

## Why the current governance digest stays unset

`APPROVED_GOVERNANCE_WRITER_SET_SHA256` remains unset. The merged collector is valid evidence that `ops-workflows` cannot presently be established as the complete authorization writer surface using only the reviewed executor capability. Selecting isolation does not turn partial evidence into trusted evidence and does not source-pin a synthetic digest.

The isolated repository will have a different writer surface and requires its own later exact setup evidence after the repository exists. No digest is derived from the dormant contract itself.

## Future owner-gated live setup — not authorized here

A later exact owner authorization must separately name the GitHub mutations required to establish the repository. Expected categories are:

- create exactly one private repository `rozkalnsandris/deploy-authorizations`;
- enable Issues if needed;
- disable GitHub Actions for that repository;
- verify/remove any unapproved collaborator or integration access before acceptance;
- select the approved owner-operated integration for explicit LIVE-AUTH creation as required;
- extend `Rozkalns Deploy Executor` selected-repository access to the isolated repository without increasing its Issues/Metadata permissions;
- capture sanitized repository identity/settings/writer evidence, including the new stable numeric repository ID.

Those are repository-settings/App-installation trust-boundary mutations. This source decision does not authorize any of them.

If the live setup cannot prove the intended writer surface without introducing a new admin credential or an unreviewed writer, preserve evidence and STOP rather than choosing another path automatically.

## Safety boundary

This source gate performs no:

- repository creation or deletion;
- repository-settings change;
- GitHub App permission or selected-repository mutation;
- PAT/user-token/private-key creation or placement;
- protected-host read;
- P8 poller/config/systemd/service/timer change;
- production registry or adapter activation;
- READY/LIVE-AUTH creation;
- authorization consumption;
- Hermes Deals runner, DB, Cloudflare, Docker, storage, network, backup, or production mutation.

Merge of this source contract, if later explicitly authorized, still authorizes none of those live actions.
