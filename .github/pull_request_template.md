## Outcome Delivery v1

- **Lane:** FAST / AUTO-RUN FULL / STRICT
- **Related outcome issue:** #...
- **Host/runtime effect:** NONE / READ_ONLY / MUTATION
- **Trust-boundary change:** YES / NO
- **Native stacked PR:** NO by default under current no-force/no-history-rewrite policy

## Outcome

State the visible end state this PR delivers.

## Coherent work items

List 2-5 closely related same-risk items included in this Outcome PR.

1.
2.

Explain briefly why they belong in one delivery unit rather than separate proof-object PRs.

## Scope

Include implementation, wiring/integration, tests, operator/preflight and docs/provenance together when they are required for the same independently useful outcome.

Split only for an independently valuable outcome, a different risk/trust boundary, a different runtime target/owner decision, or a genuinely separate coherent review unit.

## Integrated validation

List focused source/policy tests and all required security checks that validate the outcome end-to-end.

## Merge envelope

- Final intended diff frozen: YES / NO
- Base / current main:
- Exact head SHA:
- Required CI/checks:
- Unresolved review threads:
- Reviewed outcome/scope diff:
- Merge authorization: NONE / MERGE_AUTHORIZED_PENDING_CHECKS / AUTO-RUN-FULL-FROZEN
- Head drift invalidates merge authorization/readiness: YES

FAST merge authorization, when granted, must bind the exact PR head and is executed only after all repository rules/checks pass. AUTO-RUN FULL follows its frozen issue-specific authority. Merge never authorizes LIVE.

## Ready receipt

- Host/runtime classification:
- Exact post-merge verification:
- Exact next owner gate:

No PR authorizes sudo/root, packages, services/timers, Docker, networking/firewall/DNS/Cloudflare, SSH/users/mounts/kernel, backups, DB/application data, secrets, permissions, protected runtime inspection, or other LIVE mutation unless a separate exact LIVE contract authorizes it.
