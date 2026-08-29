# P9 isolated LIVE-AUTH authorization surface

Status: SOURCE ONLY / DORMANT / POST-SAVE TRUST EVIDENCE STOP
Roadmap: `RPi5_main#236`
Canonical program: `docs/AUTOMATION_MASTER_PLAN.md`

## Decision

The owner selected `P9 TRUST DECISION: ISOLATED-AUTH-SURFACE` after the merged P9 governance collector proved that the current read-only Deploy Executor credential cannot independently enumerate the complete installed-App/integration writer surface of `ops-workflows`.

P9 therefore does **not** broaden the autonomous executor with repository Administration permission, a PAT, a user token, or any other admin credential. Instead, LIVE-AUTH authority moves to a separately owner-approved isolated repository while deployment eligibility remains in `rozkalnsandris/ops-workflows`.

This document and `ops/deploy/executor-p9-isolated-auth-surface.json` are source contracts only. They do not create a repository, change repository settings, change App installation scope or permissions, place credentials, alter P8/systemd, create LIVE-AUTH, or enable production mutation.

## 2026-08-29 connector-scope reconciliation

The first separately authorized trust-boundary transaction created the private repository and then stopped fail-closed before any App selection. Sanitized evidence is recorded in `RPi5_main#191`, comment `5461784620`:

- repository `rozkalnsandris/deploy-authorizations` now exists with stable GitHub ID `1350486101`;
- visibility is private, Issues are enabled and Actions are disabled;
- direct collaborator count is zero;
- no GitHub App was installed on the repository at the STOP point;
- the one-time trust-boundary authorization is consumed.

The transaction discovered that the installed `ChatGPT Codex Connector` App ID `1144995` is not an Issues-only integration. GitHub displayed read access to checks, commit statuses and metadata, plus read/write access to actions, contents/code, issues, pull requests and workflows. Repository selection grants the App access to the selected repository under the App's registered permission set; repository selection is not a per-repository permission reducer.

The corrected least-privilege decision is therefore **owner-only LIVE-AUTH writing**:

- accepted authorization author: exact GitHub actor `type=User`, ID `277435981`;
- authoring mode: an owner-authenticated GitHub session;
- App-authored authorization issues are rejected;
- no operator/writer GitHub App is approved on the authorization repository;
- `chatgpt-codex-connector` is explicitly excluded and must remain unselected for this repository;
- only the separately reviewed read-only Deploy Executor reader may be selected.

GitHub documents that a GitHub App can make user-attributed requests on behalf of a user. User attribution does not narrow the App installation's repository permission set, so attribution alone is not accepted as containment for this authorization trust root.

Official GitHub product references reviewed for this correction:

- GitHub App permission model: <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app>;
- installed-App repository selection: <https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps>;
- repository Actions disablement: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository>;
- user-attributed GitHub App requests: <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user>.

## 2026-08-29 read-only executor repository-selection transaction

After `RPi5_main#268` merged the corrected owner-only connector-scope contract at `de68073fa2269a128b130d67e4f868d914c61a47` and exact-main Validate #646, FAST-LANE #101 and GITHUB-ONLY #90 were green, the owner separately authorized the remaining read-only repository-selection transaction.

Immediately before the Save, the owner revalidated in an owner-authenticated GitHub UI session that the isolated repository had the intended private/Issues-on/Actions-off/zero-direct-collaborator/no-writer posture. The `Rozkalns Deploy Executor` configuration page showed:

- App ID `4748870`;
- repository permissions limited to Issues read and Metadata read/minimum;
- repository access mode `Only select repositories`;
- selected repositories `rozkalnsandris/ops-workflows` and `rozkalnsandris/deploy-authorizations`;
- no permission widening.

The owner then performed exactly one Save. That mutation consumed the remaining-reader setup authorization. No `chatgpt-codex-connector` selection, writer integration, permission widening, repository-settings change, host/runtime or production mutation was authorized or reported as part of that Save.

The Save receipt is **not** accepted as final trust-surface evidence by itself. Post-save read-only verification established only a partial result:

- the current ChatGPT Codex Connector installation repository set still does not include `deploy-authorizations`, consistent with the required exclusion;
- the available connector cannot enumerate the separate Deploy Executor installation ID `157217641` and returns `403 Resource not accessible by integration` for that installation;
- the available connector also cannot independently establish the complete post-save collaborator/App administration surface of the private authorization repository.

Therefore the final writer/reader trust surface remains **NOT PROVEN**. No retry, rollback, cleanup or alternate mutation path followed the post-save evidence limitation. The machine contract deliberately remains `status=partial-stop`, `authorization_repository_id=null`, `activation_enabled=false`, `runtime_binding_ready=false`, `host_wiring_enabled=false`, and `production_mutation_enabled=false` until accepted read-only evidence closes this gate.

## Frozen repository roles

### Queue repository

`rozkalnsandris/ops-workflows` remains the canonical `DEPLOY-QUEUE` repository.

Queue state is eligibility evidence only. It is not owner execution authority. A queue mutation can never substitute for, create, or modify LIVE-AUTH authority.

Stable current queue repository ID: `1328835922`.

### Isolated authorization repository

The intended repository identity is:

`rozkalnsandris/deploy-authorizations`

The repository exists and the partial setup evidence records GitHub ID `1350486101`. The owner-performed repository-selection Save reports that the reviewed read-only Deploy Executor was added to the selected-repository set, but the complete post-save writer/reader surface has not been independently verified. Its authoritative runtime binding therefore remains intentionally **unbound**. Schema v2 rejects any non-null `authorization_repository_id` while evidence status is `partial-stop`; the machine contract keeps that field null and `activation_enabled=false`, `runtime_binding_ready=false`, `host_wiring_enabled=false`, and `production_mutation_enabled=false`.

A later source binding must use exactly the observed GitHub-assigned ID `1350486101`, but only after accepted read-only post-save evidence proves the final writer/reader surface. No synthetic ID, placeholder repository, temporary repository, name-only trust, owner Save receipt alone, or partial-setup evidence is sufficient for runtime binding.

## Required isolated-repository invariants

Before any P9 runtime binding can become Ready, fresh accepted evidence must prove all of these conditions:

- repository identity is exactly `rozkalnsandris/deploy-authorizations` plus stable numeric GitHub ID `1350486101`;
- visibility is private;
- Issues are enabled;
- GitHub Actions are disabled for the repository so no workflow can acquire `GITHUB_TOKEN` authority there;
- no unapproved human collaborator has access that can edit LIVE-AUTH Issues;
- no team writer surface exists for this user-owned repository;
- no GitHub App/OAuth/operator integration can edit Issues in the repository;
- `chatgpt-codex-connector` App ID `1144995` is not selected for the repository;
- the final installed-App surface contains only the reviewed read-only `Rozkalns Deploy Executor` reader;
- every accepted LIVE-AUTH issue has GitHub server-side actor `type=User`, ID `277435981`;
- the configured owner numeric identity remains `277435981`;
- any later change to collaborators, integrations, Actions enablement, repository visibility, or issue-write authority is a trust-boundary change that invalidates the accepted setup until separately reviewed.

GitHub documents that disabling Actions at repository level prevents workflows from running in that repository. The isolated design uses that product control to remove workflow `GITHUB_TOKEN` from the authorization writer surface instead of granting the executor Administration read solely to audit workflow settings.

## Approved writer/readers

The intended LIVE-AUTH writer set is deliberately narrow.

Owner authority:

- GitHub user ID `277435981`;
- `type=User` remains mandatory in LIVE-AUTH validation.

Approved owner-operated writer integrations:

- none.

Explicitly excluded integration:

- GitHub App ID `1144995`;
- slug `chatgpt-codex-connector`;
- observed repository permissions include read/write Actions, Contents, Issues, Pull requests and Workflows, plus read Checks, Commit statuses and Metadata;
- it must not be selected for `rozkalnsandris/deploy-authorizations`;
- neither explicit-owner invocation nor user-attributed API authorship narrows those repository permissions.

Autonomous executor reader:

- `Rozkalns Deploy Executor` App ID `4748870`;
- Issues read-only;
- Metadata read-only/minimum;
- no GitHub write permission on the authorization surface;
- webhook disabled remains the target posture;
- owner-performed selected-repository Save reports access to both `ops-workflows` and `deploy-authorizations`, but final post-save App-surface evidence remains pending.

No issue-writer integration is approved by this source decision. The only accepted writer identity is the owner User actor.

## Installation-token isolation

The queue repository and authorization repository are separate trust roles even if the same read-only Deploy Executor installation is selected for both repositories.

Future runtime source must mint repository-scoped installation tokens per role rather than turning the current one-repository P8 token into an unnecessarily broad generic token:

- queue-read token: only `rozkalnsandris/ops-workflows`, Issues read;
- authorization-read token: only `rozkalnsandris/deploy-authorizations`, Issues read;
- no token may carry Issues write or repository Administration permission.

The current P8 source and installed runtime remain bound to `ops-workflows` only. The owner-performed selected-repository Save does not alter that installed runtime configuration, and this source reconciliation does not alter it either.

## Protocol migration contract

The current LIVE-AUTH v1 implementation intentionally conflates authorization repository and queue repository through the existing `AUTHORIZATION_REPOSITORY` constant. That behavior remains unchanged so current P8/P9 code cannot silently begin consuming the isolated repository before its trust surface is accepted and source-bound.

After accepted post-save trust evidence proves the final isolated writer/reader surface, a separate source PR and schema migration must split the roles explicitly:

1. `QUEUE_REPOSITORY` remains `rozkalnsandris/ops-workflows` with stable ID `1328835922`;
2. the LIVE-AUTH repository becomes `rozkalnsandris/deploy-authorizations` plus stable repository ID `1350486101`;
3. payload `queue_repository` validation continues to require `ops-workflows`;
4. issue acceptance validates the isolated repository name **and** stable numeric ID;
5. governance acceptance no longer depends on the broad `ops-workflows` writer-set digest as the LIVE-AUTH authority surface;
6. the accepted isolated repository setup evidence becomes the trust-root prerequisite for LIVE-AUTH acceptance;
7. P8/poller/runtime client composition is updated only after that source migration is separately reviewed and merged.

Until those steps are complete, P9 remains mutation-disabled and no genuine LIVE-AUTH canary is eligible.

## Why the current governance digest stays unset

`APPROVED_GOVERNANCE_WRITER_SET_SHA256` remains unset. The merged collector is valid evidence that `ops-workflows` cannot presently be established as the complete authorization writer surface using only the reviewed executor capability. Selecting isolation does not turn partial evidence into trusted evidence and does not source-pin a synthetic digest.

The isolated repository has a different writer surface and requires accepted exact post-save evidence. No digest is derived from the dormant contract, the pre-save UI, or the owner Save receipt alone.

## Post-save evidence gate — read-only / no mutation authorized here

The remaining gate is evidence collection and verification, not another automatic setup attempt. It must prove with sanitized read-only evidence:

- exact repository identity `1350486101`, private visibility, Issues enabled, Actions disabled and zero direct collaborators;
- `chatgpt-codex-connector` and every other writer integration absent;
- final installed-App surface containing exactly `Rozkalns Deploy Executor` App ID `4748870` with Issues read + Metadata read only and no write permission;
- no other human/team/integration writer surface capable of editing accepted LIVE-AUTH authority.

If that evidence is unavailable, ambiguous, inconsistent or shows drift, preserve the evidence and STOP. Do not retry the Save, reselect repositories, widen permissions, change repository settings, roll back, clean up or choose an alternate mutation path under this source/evidence gate. Any corrective GitHub mutation requires a new exact owner authorization naming that mutation.

Only after this evidence gate passes may a separate reviewed source migration bind repository ID `1350486101` and split queue versus authorization repository roles.

## Safety boundary

This source reconciliation performs no:

- repository creation or deletion;
- repository-settings change;
- GitHub App permission or selected-repository mutation;
- PAT/user-token/private-key creation or placement;
- protected-host read;
- P8 poller/config/systemd/service/timer change;
- production registry or adapter activation;
- READY/LIVE-AUTH creation;
- authorization consumption beyond recording the historical owner Save receipt;
- Hermes Deals runner, DB, Cloudflare, Docker, storage, network, backup, or production mutation.

Merge of this source reconciliation, if later explicitly authorized, still authorizes none of those live actions.
