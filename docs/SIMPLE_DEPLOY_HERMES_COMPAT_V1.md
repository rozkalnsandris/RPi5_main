# Hermes SIMPLE-DEPLOY v1 compatibility prerequisite

Issue: `#690`

Status: **source compatibility only; Hermes is not registered as a SIMPLE-DEPLOY target and no host/runtime/LIVE mutation is authorized or performed by this source outcome.**

## Purpose

Hermes is intentionally adapted to the existing generic SIMPLE-DEPLOY v1 reconciler instead of widening the reconciler with Hermes-specific caller-controlled paths, environment, credentials, argv or commands.

The accepted Hermes consumer revision is `rozkalnsandris/hermes-deals@13f9fb69b9576d8e97ab3a85334927f3c576ca1c`. Its application Compose source uses a project-local `.env`, relative bind mounts, and a multi-service model containing `db`, `api`, `web` and profile-only `worker`. Those semantics are valid for the application repository but are not safe to expose as dynamic authority to the generic trusted host reconciler.

## Compatibility shape

`ops/deploy/simple-deploy-compose/hermes-deals-api.yml` is the RPi5-owned ordinary-deploy adapter. It deliberately contains only the `api` service.

The adapter freezes:

- project identity `hermes-deals`;
- service identity `api`;
- image identity `ghcr.io/rozkalnsandris/hermes-deals:production` as the discovery placeholder that the generic reconciler later overrides with the frozen immutable digest;
- existing external Docker network `hermes-deals_internal` and network alias `api`;
- absolute reviewed bind sources `/var/lib/rozkalns-simple-deployer/hermes-deals/data/raw` and `/var/lib/rozkalns-simple-deployer/hermes-deals/config`;
- `create_host_path: false` for both bind mounts;
- private runtime configuration lookup only through `/etc/rozkalns-simple-deployer/private/hermes-deals-api.env`;
- the existing API healthcheck.

The `/var/lib/rozkalns-simple-deployer/hermes-deals` namespace is a public-safe, fixed host-owned identity inside the generic deployer's existing state boundary. Issue #690 does not create, copy or migrate those directories or their contents; any future materialization or migration is a separate exact owner-authorized host/runtime operation.

The adapter does not define `db`, `web` or `worker`, does not contain `depends_on`, and does not enable `--remove-orphans`. Therefore the ordinary generic `docker compose ... pull api` / `up ... api` lifecycle has no Compose dependency graph through which it could recreate or restart those unrelated services.

The web and database containers remain outside this ordinary adapter. The API joins their already-existing project network; future target adoption must freshly prove that production topology before any LIVE operation.

## Private runtime configuration boundary

`ops/contracts/simple-deploy-hermes-compat-v1.json` fixes the future private runtime configuration path and the minimum required private keys:

- `DATABASE_URL`
- `HTTP_USER_AGENT`

No value for either key is stored in Git. Issue #690 does not create, read, copy or provision the private file. Any future provisioning or migration of private runtime configuration is a separate exact owner-authorized host/secret operation.

Non-secret runtime values needed by the API remain fixed in the reviewed Compose adapter (`APP_ENV`, `LOG_LEVEL`, `RAW_SNAPSHOT_DIR`, `SOURCES_CONFIG`, `HERMES_UI_ASSET_MODE`). The adapter contains no `${...}` interpolation, so caller/process environment cannot change its topology or host-path identity at parse time.

## Why the generic reconciler stays unchanged

The generic v1 reconciler already provides the required immutable-digest pull/update lifecycle for one statically allowlisted service. Hermes compatibility is achieved by narrowing the trusted Compose model, not by adding generic `--project-directory`, `--env-file`, `--no-deps`, arbitrary host-path, environment, credential, argv or shell surfaces.

Weather therefore keeps its existing registry and executor semantics unchanged.

## Source acceptance for #690

Focused tests must prove that:

1. the compatibility Compose model contains exactly `api`;
2. `db`, `web` and `worker` are absent and no dependency edge can start them;
3. private runtime configuration has one fixed `/etc/rozkalns-simple-deployer` path and no secret values are committed;
4. relative consumer bind sources are replaced by exact reviewed absolute host sources inside `/var/lib/rozkalns-simple-deployer/hermes-deals` with `create_host_path: false`;
5. the existing project network identity is static;
6. the generic executor has not gained project-directory/env-file/no-deps caller authority;
7. `ops/deploy/simple-deploy-targets-v1.json` still contains only the existing Weather target.

## Later gates

After #690 is reviewed and merged under separate merge authority, Hermes target adoption is still a separate outcome. That later source outcome must hash-pin the reviewed adapter and add the static `hermes-deals` target only after fresh GitHub revalidation.

A later LIVE/cutover decision must separately cover any required host namespace materialization, private runtime-config provisioning and exact host/runtime reconciliation. Source merge alone never provisions secrets, changes the host, starts containers, or makes Hermes LIVE through SIMPLE-DEPLOY.
