# Rozkalns Automation GitHub App contract

Status: PHASE 2 REQUIRED
Master plan: `docs/AUTOMATION_MASTER_PLAN.md`

## Purpose

`Rozkalns Automation` is the dedicated machine identity for trusted RPi5 controllers. It replaces persistent user/PAT-style GitHub API authentication for normal automation reads.

The initial app is intentionally read-only. It must not be used to push code, merge pull requests, modify workflows, read repository secrets, change repository settings, or administer runners.

## Repository installation scope

Install the app only on these repositories initially:

- `rozkalnsandris/RPi5_main`
- `rozkalnsandris/hermes-tech`
- `rozkalnsandris/rozkalns-cv`
- `rozkalnsandris/hermes-deals`

Do not install it on:

- `rozkalnsandris/hermes-email-skill` — explicitly out of automation-program scope;
- `rozkalnsandris/rozkalnsandris` — profile repository has no RPi5 production controller need.

Use **Only select repositories**, not All repositories.

## Initial repository permissions

Set exactly:

- **Actions: Read-only**
- **Contents: Read-only**

Leave all other repository permissions at **No access** for the initial installation.

Do not grant:

- Administration
- Checks write
- Commit statuses write
- Deployments write
- Environments write
- Issues write
- Pull requests write
- Secrets
- Variables write
- Webhooks write
- Workflows write

Metadata read access is implicit where GitHub requires it.

## Why these permissions are sufficient for Phase 2

The trusted local deploy controllers require only these GitHub-side facts before any local production helper can run:

1. Resolve current reviewed `main` commit:
   - `GET /repos/{owner}/{repo}/branches/main`
   - required permission: **Contents: read**.

2. Verify the target SHA has the required completed successful CI workflow run:
   - `GET /repos/{owner}/{repo}/actions/workflows/{workflow}/runs?...head_sha={sha}...`
   - required permission: **Actions: read**.

3. Verify the expected validation job exists and succeeded when the project contract requires that additional check:
   - `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs`
   - required permission: **Actions: read**.

4. Read repository content/commit identity where a local controller must verify an exact reviewed file or helper source:
   - repository contents/commit endpoints;
   - required permission: **Contents: read**.

The initial local controller does not need GitHub-side write permission to deploy. Production mutation occurs locally through narrow root-owned helpers after all exact-SHA gates pass.

## Deferred permissions

Do not pre-grant permissions for future phases.

If Hermes Deals local audit migration later proves it must resolve merged-PR metadata or trusted owner-applied audit labels, add only the minimum read permission required by that proven flow in a separately reviewed change. Prefer redesigning the local trigger to avoid new GitHub write permission.

If status/deployment reporting back to GitHub is later required, add the one specific write permission only after its endpoint and abuse boundary are documented and tested. Do not bundle write permissions into initial app creation.

## Authentication model

RPi5 stores the GitHub App private key outside every repository. The key must never be committed, pasted into issues/PRs, uploaded as workflow evidence, or placed in a public `.env`.

The controller authenticates in two stages:

1. Sign a short-lived GitHub App JWT with the private key.
2. Exchange the JWT for an installation access token for the exact installation.

Installation access tokens expire after one hour. Controllers must obtain a fresh token when needed and must not persist the installation token as a long-lived credential.

The app private key is long-lived until manually revoked, so its local file must be root-controlled or otherwise protected by a dedicated credential boundary. Rotation must be possible without changing repository code.

## Required RPi5 verification before Phase 2 exit

The Phase 2 exit gate is not satisfied merely because the app exists in GitHub UI.

From RPi5, using an installation token produced from the app identity, verify all of the following without any PAT/user token fallback:

1. token creation succeeds;
2. token expiry is present and approximately one hour from issuance;
3. the token can read `main` for each installed repository;
4. the token can list workflow runs for an exact SHA;
5. the token can list jobs for the selected successful run;
6. the installation repository list is exactly the four approved repositories;
7. no GitHub write operation is required for the read-only canary;
8. logs/evidence contain no private key, JWT, or installation access token.

The reviewed canary is `scripts/verify-github-app-readonly.py`. After the PEM has been placed at a private absolute path with mode `0600`, run only:

```bash
python3 scripts/verify-github-app-readonly.py \
  --app-id <APP_ID> \
  --installation-id <INSTALLATION_ID> \
  --key-file /absolute/private/path/rozkalns-automation.pem
```

The command fails closed if the PEM is a symlink, is group/world accessible, the token lifetime or permission set is unexpected, the installation contains an extra/missing repository, or any selected repository lacks the expected exact-main successful CI evidence. Successful output contains only PASS state, token lifetime, permission names, repository names, main SHAs and CI run IDs. It never prints the PEM, App JWT or installation access token.

Record only sanitized PASS/FAIL evidence and non-secret identifiers needed for troubleshooting.

## GitHub UI creation settings

When creating the app:

- App name: `Rozkalns Automation` if available.
- Homepage URL: a normal non-secret project/home URL may be used; it is not an authentication boundary.
- Webhook: disable unless a later reviewed phase actually needs webhooks.
- Where can this GitHub App be installed?: **Only on this account** / owner-only equivalent.
- Repository permissions: exactly **Actions read** and **Contents read**.
- Generate one private key after app creation.
- Install using **Only select repositories** and select only the four repositories listed above.

Capture the non-secret App ID and Installation ID for local configuration. Keep the downloaded PEM private key private.

## Change-control rule

Any request to add a GitHub App permission, repository, webhook, or write capability must answer:

1. Which master-plan phase requires it?
2. Which exact API endpoint needs it?
3. Why are current permissions insufficient?
4. What is the smallest permission that enables only that endpoint?
5. How is the new capability tested and rolled back?

If those answers are not recorded, do not expand the app.
