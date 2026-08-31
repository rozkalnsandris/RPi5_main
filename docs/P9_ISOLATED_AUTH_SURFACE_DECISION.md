# P9 trust decision — isolated authorization surface

Status: SOURCE DECISION / DORMANT / PARTIAL LIVE SETUP STOP
Roadmap: `RPi5_main#236`
Decision: `P9 TRUST DECISION: ISOLATED-AUTH-SURFACE`

The owner selected a separately isolated LIVE-AUTH repository rather than granting the autonomous Deploy Executor repository Administration permission or introducing a PAT/user admin token.

The repository `rozkalnsandris/deploy-authorizations` was created under a separately authorized trust-boundary transaction and has observed GitHub ID `1350486101`. The transaction proved private visibility, Issues enabled, Actions disabled, zero direct collaborators and zero installed GitHub Apps, then stopped before App selection when the actual `ChatGPT Codex Connector` permission set contradicted the Issues-only source assumption. Sanitized evidence is in `RPi5_main#191`, comment `5461784620`.

The corrected decision excludes `chatgpt-codex-connector` App ID `1144995` from this repository because its installation has broader repository write permissions for Actions, Contents/code, Issues, Pull requests and Workflows. LIVE-AUTH writing is owner-only: GitHub actor `type=User`, ID `277435981`, through an owner-authenticated GitHub session. No operator/writer integration is approved.

`rozkalnsandris/ops-workflows` remains the deploy-queue eligibility repository. LIVE-AUTH authority moves only after a separately authorized remaining setup transaction freshly proves the owner-only writer surface, keeps the connector absent, adds only the read-only `Rozkalns Deploy Executor` reader, and a later reviewed source migration binds exact repository ID `1350486101`.

The machine contract intentionally keeps `authorization_repository_id=null` and all activation/runtime/host/production flags false. The observed ID is setup evidence, not runtime authority.

Current P8/P9 runtime remains unchanged and bound to `ops-workflows`; production dispatch remains outside this decision. See `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_ISOLATED_AUTH_SURFACE.md` and `ops/deploy/executor-p9-isolated-auth-surface.json` for the detailed contract.

This file authorizes no repository creation/settings mutation, GitHub App installation/permission/repository-selection change, credential placement, host/systemd/P8 mutation, LIVE-AUTH creation, authorization consumption, or production mutation.
