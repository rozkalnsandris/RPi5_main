# Hermes Deals origin pull-helper first install

## Purpose

This document defines the narrow source contract that closes the prerequisite gap exposed by the Phase 4 local runtime preflight. It does not claim current host state and it does not authorize installation.

The owner-controlled root preflight on exact `RPi5_main` source `e23234f7a9308211a0d964a791e2b0f70b587818` returned `FAIL_CLOSED` before any mutation because `/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json` was absent. Focused read-only follow-up then found that the complete runner-independent helper bundle had never been installed: helper, probe, registration, evidence root, and fixed `rpi5` evidence directory were absent. That receipt recorded no filesystem/systemd mutation, credential-content read, GitHub API request, socket request, helper execution, privileged dispatch, or genuine audit.

This is expected unfinished provisioning from the Hermes Deals #834 / PR #840 source contract, not a reason to weaken the runtime preflight. PR #840 merged the runner-independent helper at exact Hermes source `2f47f64ab15e767f4e53ad182326e64e313d5094` and explicitly deferred helper installation to a later source/live slice.

## Reviewed Hermes provenance

The installer binds exactly the PR #840 merged source checkpoint, not a moving Hermes `main`:

- repository: `rozkalnsandris/hermes-deals`;
- reviewed source SHA: `2f47f64ab15e767f4e53ad182326e64e313d5094`;
- helper source: `tools/runner/origin_path_rpi5_pull_helper.py`;
- helper Git blob: `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- helper SHA-256: `f2f6e4ca823eb6c0872de0a5e92531ebacb076c48934c80654d84f3ef6f7e625`;
- probe source: `tools/hermes_deals_origin_probe.py`;
- probe Git blob: `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`;
- probe SHA-256: `96a8b5819ec85f27095c535f1a3be6cba7bac0e2a40a1132869fb39dc669ad43`.

The fixed trusted source checkout is `<RPi5-checkout-parent>/hermes-deals-origin-pull-trusted`. It is not caller-selectable. Installer preflight requires exact HEAD `2f47f64...`, detached mode, clean status, exact origin URL, and ancestry from local `origin/main`. Source bytes are read only from the exact Git object and must match both reviewed Git blob and SHA-256 identities.

## Exact first-install surface

The installer is `scripts/install-hermes-deals-origin-pull-helper.py`. Default invocation is read-only preflight. `--apply` is root-only and remains a later separate LIVE owner gate.

Four first-install directories are owned by this slice and must all be absent before apply:

1. `/var/lib/hermes-deals-audits` — `root:root 0700`;
2. `/var/lib/hermes-deals-audits/origin-path-audit` — `root:root 0700`;
3. `/var/lib/hermes-deals-audits/origin-path-audit/evidence` — `root:root 0700`;
4. `/var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5` — `root:root 0700`.

Three first-install files are owned by this slice and must all be absent before apply:

1. `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch` — exact helper, `root:root 0755`;
2. `/usr/local/libexec/hermes-deals-audits/origin-path-probe.py` — exact probe, `root:root 0755`;
3. `/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json` — exact generated registration, `root:root 0600`.

The registration binds only schema `rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1`, capability `origin-path-audit`, reviewed Hermes SHA `2f47f64...`, and the exact helper/probe SHA-256 identities. Its canonical bytes are additionally frozen by SHA-256 `b92564a93d67098c9ec264e88d48096ae1323430547ed14b6d22b590ac8591bc` and Git blob `eac8778b2c09e191ca2d3abac3a4f5e243cd41c3`.

Existing owned targets are never adopted, replaced, chmodded, chowned, or reconciled by this first-install operator. Any existing target fails closed and requires a separate reviewed reconciliation gate.

## Shared parents

The installer may only validate, never mutate, these shared parents:

- `/usr/local/sbin` — `root:root 0755`;
- `/usr/local/libexec/hermes-deals-audits` — `root:root 0755`;
- `/etc/hermes-deals-audits.d` — `root:root 0755`;
- `/var/lib` — `root:root 0755`.

The historical `tools/runner/install-origin-path-rpi5-audit.sh` is not a substitute. It installs the legacy runner dispatcher/config/sudoers surface and does not create the runner-independent registration. Reusing it would widen scope and regress the migration trust boundary.

## Fail-closed mutation semantics

The fixed installer budget is exactly four directory materializations plus three file materializations. Files use exclusive creation and fixed bytes/modes. The operator exposes no systemd operation, credential operation, GitHub API request, socket request, helper execution, audit execution, deploy, DB/data write, runner mutation, generic command, path, argv, or environment authority.

There is no automatic retry, rollback, or cleanup. After the first owned target creation starts, any error leaves the public receipt with `mutation_started=true` and exact completed materialization counts; the operator must STOP. A later repair would require new evidence and explicit authorization.

## Trusted Hermes checkout boundary

The installer does not create or update its Hermes source checkout. Before its first preflight, a separate LIVE scope must prepare exactly `<RPi5-checkout-parent>/hermes-deals-origin-pull-trusted` from `<RPi5-checkout-parent>/hermes-deals` using only a fresh `git fetch origin main` and one detached worktree creation at exact `2f47f64...`. Reset, rebase, clean, force, stash, arbitrary checkout path, or alternate source SHA are outside that scope.

Checkout preparation is therefore a separate mutation from root installation. A checkout error cannot silently fall through into installer apply.

## Runtime preflight correction

The local runtime preflight now validates both the evidence root and the fixed `/evidence/rpi5` machine directory as `root:root 0700`, matching the Hermes #834 helper contract. It remains read-only and deliberately does not prove Source App installation scope or production replay/host-observation adapters.

## Gate sequence

1. Finish this source slice through focused tests, Draft PR, exact-head CI/review and Ready.
2. STOP for explicit `MERGE`.
3. Freshly verify merged `RPi5_main/main` and exact-main CI.
4. If needed, separately LIVE-converge the RPi5 trusted checkout to that merged source.
5. Separately LIVE-create the fixed Hermes trusted detached checkout at `2f47f64...` after fresh `origin/main` retrieval.
6. Run the helper installer once in default read-only mode. A failure is fail-closed and is not apply authority.
7. Only a successful helper-install preflight may lead to a separate explicit root LIVE `--apply` authorization for exactly the 4+3 target budget.
8. After successful install, verify all seven targets read-only and only then run a fresh local runtime prerequisite preflight. The previous failed preflight is not retry authority.
9. Only `HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY` may advance to the separate Source App/protected-credential and production-adapter source decision.

Broker entrypoint wiring, privileged dispatch, helper/audit execution, genuine canary, retained evidence creation, runner retirement, deployment, credential/App permission changes, and production data mutation remain separate gates.
