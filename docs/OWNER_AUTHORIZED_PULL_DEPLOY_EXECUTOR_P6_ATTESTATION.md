# Owner-authorized deploy executor v1 — P6 exact-main attestation

Status: **P6 SOURCE ATTESTATION — NO LIVE AUTHORITY**
Roadmap: `RPi5_main#236`

This document refreshes the cross-repository compatibility evidence after P5 was squash-merged. It does not install, enable, dispatch or authorize the executor. It creates no GitHub App, permission, credential, LIVE-AUTH issue, host file, service, timer, sudo/root boundary, production adapter, database write, Cloudflare change or deployment mutation.

## Attested runtime source

The executor runtime/source identity carried forward from the merged P5 implementation is:

- repository: `rozkalnsandris/RPi5_main`
- exact source SHA: `cef684e8cde2da00de2f1591c58647a868e6acf3`
- P5 PR: `RPi5_main#244`
- merge type: squash
- commit verification: GitHub verified

This SHA is an **installation-candidate source identity only** for a future P8 review. It is not permission to install or execute anything. A P6 documentation/attestation commit does not silently replace this runtime-source identity. P8 must freshly revalidate the exact source and all bound cross-repository identities before any installation.

Exact-main checks on `cef684e8cde2da00de2f1591c58647a868e6acf3`:

- Validate run `33147154701` / run number `589`: **SUCCESS**
- Gitleaks job: **SUCCESS**
- public automation baseline job: **SUCCESS**
- FAST-LANE policy drift run `33147154712` / run number `44`: **SUCCESS**
- GITHUB-ONLY policy drift run `33147154776` / run number `33`: **SUCCESS**

## Authorization-surface attestation

Fresh current main remains:

- repository: `rozkalnsandris/ops-workflows`
- exact SHA: `c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8`
- stable repository ID: `1328835922`

Exact-main push checks:

- Policy Merge Gate run `33122863889`: **SUCCESS**
- LIVE-AUTH contract run `33122863915`: **SUCCESS**
- Validate shared automation run `33122864076`: **SUCCESS**

P5-bound source identities still resolve unchanged at this exact main:

- deploy queue template blob: `5db2f30c9906e56918ce32af96cb6454ca201807`
- LIVE-AUTH policy blob: `ddfee69cf04d4b7fbd2a46fce6ae30eace6496e6`
- LIVE-AUTH schema blob: `b1b3ab2be8b578a64fb92be01a8fd8be7ae71240`

The effective authorization-reader trust model remains the merged P0/P3 model: Issues read-only on the accepted authorization surface. Historical roadmap prose proposing Issues write is superseded and is not revived by P6.

## First-target attestation

Fresh current main remains:

- repository: `rozkalnsandris/rozkalns-cv`
- exact SHA: `d25730b20c41edff29a83927bff386751f053cd0`
- stable repository ID: `1325237749`

Exact-main push checks:

- CI run `32900880228`: **SUCCESS**
- GITHUB-ONLY policy drift run `32900880639`: **SUCCESS**

P5-bound source identities still resolve unchanged at this exact main:

- pull preflight blob: `2592e4e38e933f01409d5816c05defd22e661f6c`
- exact-SHA pull helper blob: `c787789e77c31576310bed28da0fbc893cfabb5f`
- deploy library blob: `ade60abbfea3cf56b1a56bbc1b2e0669b1a1b983`
- pull-deploy installer blob: `0f61e8d0eddb413c86beeb0eee6ded4b1f3161d5`

The P5 compatibility decision is unchanged: the existing autonomous CV controller is not the owner-authorized executor adapter because it resolves current `origin/main` itself. Only the lower-level exact-SHA helper contract is compatible with a future fixed adapter, and it requires `rollback_policy=BUILTIN_TRANSACTIONAL_V1`.

## Compatibility result

Cross-repository source compatibility after P5 merge: **PASS**.

The following invariants remain true:

1. READY is eligibility only and never deployment authority.
2. Deferred execution requires a separate owner-authored LIVE-AUTH.
3. The authorization reader remains read-only on the authority surface.
4. Poller-to-privileged IPC carries request/authorization identity only.
5. The privileged side must independently revalidate LIVE-AUTH, queue, exact source, CI, target baseline and static registry.
6. The production operation registry remains `execution_enabled=false` with zero production operations.
7. The P5 CV adapter remains dormant and its `apply()` is mutation-disabled.
8. The proposed executor systemd unit remains source-only and uninstalled.
9. GitHub receipt/result writing remains non-authority and disabled.
10. No merge, READY state or attestation authorizes P7/P8/P9/P10.

## P6 exit boundary

P6 is complete only after this attestation/governance source change itself is reviewed, merged and exact-main CI is green. Until then, P6 is source work in progress.

After P6 completion, the next executor roadmap step is **P7 — GitHub App creation/permission gate**, which is an explicit **LIVE STOP**. It requires a separate owner authorization and a fresh authorization-surface governance audit. Bare `turpini`, Ready, PR merge, this attestation, or prior LIVE-ALL semantics do not authorize P7.
