# P9 trust decision — isolated authorization surface

Status: SOURCE DECISION / DORMANT
Roadmap: `RPi5_main#236`
Decision: `P9 TRUST DECISION: ISOLATED-AUTH-SURFACE`

The owner selected a separately isolated LIVE-AUTH repository rather than granting the autonomous Deploy Executor repository Administration permission or introducing a PAT/user admin token.

The intended future repository is `rozkalnsandris/deploy-authorizations`. It is not created by this source decision. Its GitHub-assigned numeric repository ID is intentionally unknown until a later separately owner-authorized trust-boundary setup transaction.

`rozkalnsandris/ops-workflows` remains the deploy-queue eligibility repository. LIVE-AUTH authority moves only after the isolated repository exists, is proven private with Issues enabled and Actions disabled, has no unapproved writer, and a later reviewed source migration binds its exact stable repository ID.

Current P8/P9 runtime remains unchanged and bound to `ops-workflows`; production dispatch remains outside this decision. See `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_ISOLATED_AUTH_SURFACE.md` and `ops/deploy/executor-p9-isolated-auth-surface.json` for the detailed contract.

This file authorizes no repository creation/settings mutation, GitHub App installation/permission/repository-selection change, credential placement, host/systemd/P8 mutation, LIVE-AUTH creation, authorization consumption, or production mutation.
