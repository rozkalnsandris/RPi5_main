# rozkalns-cv SIMPLE-DEPLOY compatibility and first adoption v1

Status: **SIMPLE-DEPLOY observed live; legacy reconciliation remains separately owner-gated**  
Follow-up: #913 retires only the stale legacy cvbot/state/controller residue after fresh runtime evidence proved SIMPLE-DEPLOY ownership.

## Operator model

The steady-state delivery path remains intentionally small:

`consumer merge → SIMPLE-DEPLOY → production`

The one-time legacy adoption is an internal transition only. After it succeeds, future CV releases use the ordinary generic SIMPLE-DEPLOY target.

## Why the private env needs an /etc boundary

The generic SIMPLE-DEPLOY service runs as the dedicated `rozkalns-simple-deployer` user with `ProtectHome=true`.

Docker Compose reads an `env_file` itself. Relative `env_file` paths are resolved from the Compose file directory. Therefore the CV app env cannot safely remain an `env_file` under a protected account home that the service cannot traverse.

The reviewed adapter now uses:

`../private/rozkalns-cv.env`

from the installed Compose file at:

`/etc/rozkalns-simple-deployer/compose/rozkalns-cv.yml`

which resolves to:

`/etc/rozkalns-simple-deployer/private/rozkalns-cv.env`

The protected boundary is:

- parent: `/etc/rozkalns-simple-deployer/private`, `root:rozkalns-simple-deployer`, mode `0750`;
- file: `/etc/rozkalns-simple-deployer/private/rozkalns-cv.env`, `root:rozkalns-simple-deployer`, mode `0640`;
- source discovery: exactly one passwd home containing both fixed relative paths `docker/cv/bot/.env` and `docker/cv/bot/data`;
- preflight: metadata only; secret contents are not read or emitted;
- LIVE materialization: the reviewed fixed helper copies the private env bytes without logging them and does not modify the source file;
- public non-secret overrides remain in Compose: `LLM_BASE_URL=https://api.openai.com` and `LLM_MODEL=gpt-5.6-luna`.

Reviewed helper:

`scripts/materialize-simple-deploy-rozkalns-cv-private-env-v1.py`

This is part of the one-time cutover, not a second owner-facing deploy phase.

Official references:

- Docker Compose `env_file`: https://docs.docker.com/reference/compose-file/services/#env_file
- Docker bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- systemd `ProtectHome=`: https://www.freedesktop.org/software/systemd/man/systemd.exec.html#ProtectHome=

## Durable data remains in place

The existing persistent data directory is **not copied, migrated, reowned or deleted**.

The source adapter keeps only one host-local Compose interpolation value:

`ROZKALNS_CV_DATA_PATH`

The resolved absolute path is written to:

`/etc/rozkalns-simple-deployer/compose/.env`

That file contains path metadata only, not app secrets.

Docker bind mounts are created on the Docker daemon host. The generic deployer therefore passes the reviewed host path to Docker while the durable data remains at its existing host location. The bind keeps `create_host_path: false`, so a missing source fails closed instead of creating an empty directory.

The legacy and candidate `bot/storage.py` Git blob remains identical:

`7a7ce05021223b43686cd93513208bb0a249d9bc`

Both runtimes use application UID/GID `10001:10001`. No database query or schema migration is part of the cutover.

## Current observed live release

Fresh read-only evidence on 2026-10-08 established:

- consumer: `rozkalnsandris/rozkalns-cv`;
- live source revision: `6c226ac797602007b960da8dad114f794f450717`;
- immutable live image digest: `sha256:dd33f110db46f92953241680bf86b475cdbb10fd76ec7f5e5ec6299ea2a97480`;
- Compose project/service: `rozkalns-cv/cv`;
- loopback ownership: `127.0.0.1:8088`;
- liveness and readiness: HTTP 200;
- stale legacy `cvbot`: restart-looping from `rozkalns-cv-cvbot:8661337c1020c4d70e1da129209c5ffd7ad9bf7e`;
- stale legacy production state: `4986a6d80460bd6d7681c70e09e61a15e31007f4`;
- legacy pull timer/service: disabled/inactive.

The former one-time cutover candidate is historical provenance only. It is superseded by the observed live SIMPLE-DEPLOY runtime and is no longer registered as an executor operation.

## Post-cutover reconciliation (#913)

Reviewed source entrypoint:

`ops/bin/rozkalns-cv-post-cutover-reconcile`

Default `check` mode is read-only. A later `apply` requires separate exact LIVE authority and the explicit confirmation token.

The future mutation envelope is smaller than the original cutover:

1. prove exact RPi5 source binding and exact healthy SIMPLE-DEPLOY CV source/digest/port ownership;
2. prove exact residual legacy `cvbot`, stale production state, disabled/inactive legacy controller and the 12 allowlisted retirement-file metadata invariants;
3. stop and non-force remove only legacy `cvbot`;
4. remove only those 12 stale legacy state/controller files;
5. run only `systemctl daemon-reload` for systemd reconciliation;
6. prove the live SIMPLE-DEPLOY container ID/source/digest/port and HTTP health did not change.

The operator does not target private env files, persistent CV data, database/application data, SIMPLE-DEPLOY receipt/Compose/registry runtime state, deploy evidence/backups, Cloudflare or network state.

## Historical one-time legacy adoption

The STRICT cutover remains one owner-authorized operation:

1. revalidate exact RPi5/CV source, CI, production pointer, legacy containers, port ownership and existing env/data metadata;
2. materialize and verify the protected CV env boundary **before legacy retirement**;
3. quiesce the generic SIMPLE-DEPLOY timer and install the Weather+CV registry, exact RPi5 identity, reviewed CV Compose and data-path-only interpolation metadata;
4. retire the exact legacy `cvbot` and `cv` containers and require `127.0.0.1:8088` to become unbound;
5. invoke generic SIMPLE-DEPLOY for the exact immutable candidate;
6. require receipt identity, liveness/readiness HTTP 200 and the public UI v2 marker;
7. restart the generic SIMPLE-DEPLOY timer only after successful verification.

If private-env materialization fails, legacy runtime retirement has not started. After any mutation error the process remains fail-closed: no automatic retry, cleanup, rollback or alternate deployment path.

## Authority boundary

This source change does **not** authorize:

- private env materialization on the host;
- secret content display or repository publication;
- legacy runtime retirement;
- Docker/Compose execution;
- production deploy;
- persistent-data copy/migration/reownership/deletion/content inspection;
- database query/schema/data migration;
- Cloudflare/network mutation;
- repository settings/permissions/secrets mutation.

The cutover itself is historical. A later post-cutover reconciliation requires separate exact owner LIVE authorization bound to the final merged RPi5 source and the exact observed live CV source/digest.