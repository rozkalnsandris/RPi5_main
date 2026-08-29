# P9 isolated LIVE-AUTH authorization surface

Status: SOURCE ONLY / DORMANT / PARTIAL LIVE SETUP STOP
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
- only the separately reviewed read-only Deploy Executor reader may be selected later.

GitHub documents that a GitHub App can make user-attributed requests on behalf of a user. User attribution does not narrow the App installation's repository permission set, so attribution alone is not accepted as containment for this authorization trust root.

Official GitHub product references reviewed for this correction:

- GitHub App permission model: <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app>;
- installed-App repository selection: <https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps>;
- repository Actions disablement: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository>;
- user-attributed GitHub App requests: <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user>.

## Frozen repository roles

### Queue repository

`rozkalnsandris/ops-workflows` remains the canonical `DEPLOY-QUEUE` repository.

Queue state is eligibility evidence only. It is not owner execution authority. A queue mutation can never substitute for, create, or modify LIVE-AUTH authority.

Stable current queue repository ID: `1328835922`.

### Isolated authorization repository

The intended repository identity is:

`rozkalnsandris/deploy-authorizations`

The repository now exists and the partial setup evidence records GitHub ID `1350486101`. Its authoritative runtime binding remains intentionally **unbound** because the writer/reader surface has not completed the revised owner-only acceptance gate. Schema v2 rejects any non-null `authorization_repository_id` while evidence status is `partial-stop`; the machine contract keeps that field null and `activation_enabled=false`, `runtime_binding_ready=false`, `host_wiring_enabled=false`, and `production_mutation_enabled=false`.

A later source binding must use exactly the observed GitHub-assigned ID `1350486101`, but only after a separately authorized remaining setup transaction proves the revised writer/reader surface. No synthetic ID, placeholder repository, temporary repository, name-only trust, or partial-setup evidence is sufficient for runtime binding.

## Required isolated-repository invariants

Before any P9 runtime binding can become Ready, the authorization repository must be freshly proven to satisfy all of these conditions in one owner-authorized trust-boundary transaction:

- repository identity is exactly `rozkalnsandris/deploy-authorizations` plus its fresh stable numeric GitHub ID;
- visibility is private;
- Issues are enabled;
- GitHub Actions are disabled for the repository so no workflow can acquire `GITHUB_TOKEN` authority there;
- no unapproved human collaborator has access that can edit LIVE-AUTH Issues;
- no team writer surface exists for this user-owned repository;
- no GitHub App/OAuth/operator integration can edit Issues in the repository;
- `chatgpt-codex-connector` App ID `1144995` is not selected for the repository;
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
- webhook disabled remains the target posture.

No issue-writer integration is approved by this source decision. The only accepted writer identity is the owner User actor.

## Installation-token isolation

The queue repository and authorization repository are separate trust roles even if the same read-only Deploy Executor installation is later selected for both repositories.

Future runtime source must mint repository-scoped installation tokens per role rather than turning the current one-repository P8 token into an unnecessarily broad generic token:

- queue-read token: only `rozkalnsandris/ops-workflows`, Issues read;
- authorization-read token: only `rozkalnsandris/deploy-authorizations`, Issues read;
- no token may carry Issues write or repository Administration permission.

The current P8 source and installed runtime remain bound to `ops-workflows` only. This PR does not alter that installed configuration.

## Protocol migration contract

The current LIVE-AUTH v1 implementation intentionally conflates authorization repository and queue repository through the existing `AUTHORIZATION_REPOSITORY` constant. That behavior remains unchanged in this source-decision gate so current P8/P9 code cannot silently begin consuming the isolated repository before its trust surface is completed and source-bound.

After the remaining trust-boundary setup has been completed and stable ID `1350486101` has been freshly revalidated, a separate source PR and schema migration must split the roles explicitly:

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

The isolated repository has a different writer surface and requires its own later exact setup evidence after the remaining trust-boundary setup is completed. No digest is derived from the dormant contract itself.

## Future owner-gated live setup — not authorized here

A later exact owner authorization must separately name only the remaining GitHub trust-boundary mutations and revalidation required to complete setup:

- freshly revalidate exact repository identity `1350486101`, private visibility, Issues enabled, Actions disabled and zero direct collaborators;
- prove `chatgpt-codex-connector` and every other writer integration remain absent;
- extend `Rozkalns Deploy Executor` selected-repository access to the isolated repository without increasing its Issues/Metadata read-only permissions;
- prove the final installed-App surface contains only that reviewed read-only executor;
- capture sanitized repository identity/settings/writer/reader evidence and STOP.

Those are repository-settings/App-installation trust-boundary mutations. This source decision does not authorize any of them.

If the remaining live setup cannot prove owner-only writing plus the single reviewed read-only executor without introducing a new admin credential or any writer integration, preserve evidence and STOP rather than choosing another path automatically.

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
