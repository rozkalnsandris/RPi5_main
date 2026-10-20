# GitHub-first / RDC fallback adoption — RPi5_main

Status: proposed source-only consumer adoption; effective in `RPi5_main` after explicit owner merge.
Canonical shared baseline: `rozkalnsandris/ops-workflows@4e89b75d7f496dfb43fd9c1eb10a995fad53fdd8`.
Normative shared contract: `docs/GITHUB_FIRST_RDC_FALLBACK_V1.md`.
Machine shared policy: `policy/github-first-rdc-fallback-v1.json`.
Local adapter: `.github/github-first-rdc-v1.json`.
Tracking: `RPi5_main#1134`.

## Required tool routing

1. For **each work step**, choose connected GitHub operations when they provide equivalent correctness/evidence. Source, files, branches/commits, issues, PRs, checks, reviews and canonical continuity remain GitHub-side.
2. Run source tests with GitHub Actions when equivalently supported; do not use the RPi5 shell just for convenience, speed, habit or an available `git`/`gh`/`curl`.
3. Only when GitHub and applicable GitHub-hosted CI **cannot** perform a required **host-local** step, record the precise capability gap and allowed minimum RDC operation, plus the applicable existing read/LIVE authorization. No proof or authority means **STOP**.
4. Perform only that bounded host-local step, record non-sensitive evidence, and return to GitHub. The pattern is **GitHub -> minimal RDC -> GitHub**.
5. GitHub `403`/`429`, rate limit, permission denial, timeout, uncertain write outcome or missing authorization is **STOP**, not an alternate RDC route.

Before RDC, record `STEP`, `REPOSITORY_AND_TARGET`, `GITHUB_CAPABILITY_CHECKED`, `PRECISE_CAPABILITY_GAP`, `GITHUB_CI_NOT_EQUIVALENT_REASON`, `MINIMAL_RDC_OPERATION`, `EXISTING_AUTHORIZATION`, and `GITHUB_RETURN_EVIDENCE`. Never publish credentials, protected runtime data or private path contents.

## Local stricter boundaries

`AGENTS.md` production and forbidden-data safety still wins. RDC is not a shortcut to protected data, service/Docker/systemd mutation, network changes or host privileges. Source authorization does not grant merge. Merge does not grant LIVE. An exact LIVE envelope is required for RPi5 runtime mutation. No retry/rollback/cleanup on mutation errors without pre-authorized authority.

This regular GitHub-first priority **does not** activate the distinct deferred-LIVE `GITHUB-ONLY` mode, `AUTO-RUN FULL`, a deployment or a new executor. This adoption adds source policy, local machine routing and CI tests only. The shared contract does not automatically modify other consumer repositories.
