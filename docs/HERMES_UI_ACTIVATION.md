# Hermes UI activation through existing tools — #1023

Status: **SOURCE PREPARATION ONLY**. This is not a host execution packet or
permission to deploy. Source merge neither selects nor installs the enabled
adapter. The existing UI-off adoption operator and target registry are unchanged.

## Reuse the ordinary deploy path

First complete the existing [state adoption](HERMES_STATE_ADOPTION_V1.md) and
invoke the installed public SIMPLE-DEPLOY CLI as its existing runtime principal:

```sh
/usr/local/libexec/rozkalns-simple-deployer/rozkalns-simple-deployer --target hermes-deals
```

Use only a reviewed UI-gated release (Hermes #998 or its reviewed successor).
Verify the actual API image, health and collector write/read path before UI
activation. The generic executor owns its target lock, image resolution and
receipt. Do not call its private methods, wrap its lock or build another deployer.
Keep competing manual deployment and collector writers quiescent for the agreed
maintenance window. Ordinary deployment does not migrate the database.

## Existing migration, exact destination

Hermes already packages `/app/alembic.ini` and the unchanged migration
`0008_household_state` in its API image. Its parent is
`0007_comparison_family_pricing`; it adds only `household_states`.

Before production execution, the single LIVE packet must bind the selected image
and container, permit the DB write, and include:

- a pre-change DB audit and identified backup with a successful isolated restore;
- exactly one Alembic head at `0007_comparison_family_pricing`, with no
  `household_states` table; unknown or partially applied state stops;
- a tested migration on the restored PostgreSQL database using that same image,
  with retailer observations preserved and the new table/constraints verified.

Run the existing command **inside the identity-verified API container**, from
`/app`, using its existing database configuration; never print or pass the DB
URL on the command line:

```sh
python -m alembic upgrade 0008_household_state
```

Do not use `upgrade head`, `stamp` or `downgrade`. If the database already has
exactly head `0008_household_state`, validate table/schema compatibility and skip
the migration. An unrelated head or malformed table is not an invitation to fix
it automatically. Preserve evidence and stop after an execution error; rollback,
restore and retry need the recovery terms agreed in the LIVE packet.

This uses the existing Alembic entrypoint instead of adding a migration service
or controller. The host invocation, backup/restore procedure and sanitized audit
commands still need to be frozen in the concrete LIVE packet; this document alone
does not establish those prerequisites or authorize their execution.

## Opt-in adapter and one-time configuration transition

Candidate: `ops/deploy/simple-deploy-compose/hermes-deals-household-enabled-api.yml`.
SHA-256: `6d722f377562f4dcb74941be2df3cabeb17cd2b5dd0499df5f29a73c4c735c90`.
Its only difference from the adopted household adapter is the explicit string
`HERMES_HOUSEHOLD_UI_ENABLED: "1"`. Household `home`, public origin, the two-key
private env projection, volumes, network, health and API-only scope are preserved.

Only after schema and access prerequisites pass, the concrete LIVE packet must:

1. Install this reviewed candidate under the fixed SIMPLE-DEPLOY compose root.
2. Update only the installed `hermes-deals` target's compose filename and hash.
   Preserve every other target/global setting. Do not replace the installed
   registry with a whole-repository candidate or edit the adoption baseline.
3. Recreate only the API with its already verified immutable digest and the
   new adapter, using the existing Compose project and digest override. The
   bounded command must include `--no-deps --force-recreate --pull never --no-build`;
   the exact files/argv are frozen after checking the installed executor layout.
   Never let the candidate's `production` discovery tag select a different image
   during this configuration-only step.
4. Verify the same image, mounts, health, enabled route and valid target state.

A normal same-digest reconcile may return `NO_OP_CURRENT`; it is not proof that
changed configuration was applied. The configuration transition is a one-time
operation, not a replacement release path. Later image releases keep using the
ordinary public SIMPLE-DEPLOY command and its normal receipt semantics.

## Acceptance and remaining work

Verify the private access boundary, `/ui`, `/ui/home/`, assets, forms and mobile
layout. In an explicitly permitted test household, verify persistence across two
sessions, stale-version rejection, origin/CSRF, store/price selection and meal
flows. Include test-data creation/removal in the LIVE scope. Verify collector
selection and source freshness before restoring the agreed collector timers.
Changing `/` to make the new UI the default is a separate product decision.

Remaining: current host baseline, backup/restore evidence, frozen target-only
file update/recreate commands and runtime acceptance. No new controller, timer,
generic executor change or additional per-command approval is required by this
source proposal. One bounded owner decision should cover the complete reviewed
maintenance window once these concrete details are ready.
