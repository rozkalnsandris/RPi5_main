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

### Existing household ingress — #1025

The legacy host source file can match the known W4 Nginx configuration without
the household routes. A source-file hash alone does not prove which file is bound
into the running `web` container or which configuration its workers loaded.
The API-only SIMPLE-DEPLOY adapter does not update that independent ingress.

Reuse the existing [Hermes household Nginx configuration](https://github.com/rozkalnsandris/hermes-deals/blob/a30d7f1b866f70da9f047cd117f2cf584ffcf4a7/infra/nginx.conf),
SHA-256 `0aa93632d9c5af8effe5f3b37ef581f62906a2508e1b17252956979f71e342c5`.
Relative to the known W4 baseline
`c3c27c91037895002f15e82f049fcc24b274ac93857e573ff62f6236c797a5ae`,
its only change is the existing `/ui/home` and `/ui/home/` proxy blocks.
The `/` redirect remains `/ui`. Do not add another proxy or change DNS, Tunnel,
ports, authentication or the generic deployer.

The replacement LIVE packet must include this ingress operation explicitly:

1. Before any mutation, identify exactly one running Hermes `web` container by
   project/service labels. With explicitly authorized, filtered inspection,
   prove its single-file read-only bind maps the fixed host
   `passwd(andris).home/hermes-deals/infra/nginx.conf` to
   `/etc/nginx/conf.d/default.conf`. Compare only bounded known-source hashes
   inside and outside the container; never print raw config or full inspect.
   Require the exact known baseline, unchanged regular single-link source inode,
   trusted ancestors, expected metadata and a successful existing `nginx -t`.
   Unknown mounts/configuration stop before mutation.
2. For this confirmed single-file bind, preserve the mounted inode when replacing
   its contents with the exact reviewed candidate; validate metadata and original
   bytes again immediately before the bounded write, fsync, then verify the
   candidate hash through both host and container paths. Atomic path replacement
   alone leaves a file bind mounted to the old inode and is not sufficient.
   This is an explicitly authorized in-place configuration write, not a generic
   installer; interruption can leave partial disk content even while old workers
   keep serving. Preserve evidence and stop on error; no implicit retry/rollback.
3. After the API transition is healthy and the candidate is visible inside that
   same container, run standard `nginx -t`, then one `nginx -s reload`, using
   `docker exec` against the identity-verified container. Capture sanitized
   outcomes only. Reload also resolves the `api` upstream after API recreation.
   No web/container restart or recreation is required for this inode-preserving
   path. Freeze the exact invocation and validation in the new LIVE packet.
4. Verify actual HTTP routing through `web`, household assets/forms and the
   external access boundary. A successful signal or matching file hash alone is
   not evidence of a successful worker reload. Any failed postcheck stops the
   remainder of the session under its declared recovery terms.

The earlier packet excluded Nginx writes/reloads and used the former raw-file
limit. It remains stopped. Do not append mutations to that authorization or
silently replace its pinned launcher. After source merge, prepare one replacement
packet with the new adoption source/limits and this ingress step alongside the
already planned backup, migration, API activation and collector acceptance.

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
