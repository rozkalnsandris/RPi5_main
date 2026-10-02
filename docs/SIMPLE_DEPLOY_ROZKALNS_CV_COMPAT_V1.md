# rozkalns-cv SIMPLE-DEPLOY compatibility and first adoption v1

Status: **source-ready only; LIVE remains separately owner-gated**  
Follow-up: private-env accessibility correction after the read-only #821 cutover preflight.

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

## Current exact release

- consumer: `rozkalnsandris/rozkalns-cv`;
- source: `d75863d0ce4cfdac0015150137523abbaccf5914`;
- immutable image digest: `sha256:ba9e24c82eccd833cfe42d6a4aa61ef76c584bcfd4c27efbced13c3a408d2a1a`;
- shared SIMPLE-DEPLOY workflow: `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- target: `rozkalns-cv-rpi5`;
- RPi5 Compose SHA-256: `d4c7e9ed5c36245d92ce7da199194ec032c74de6ea03f2b522e31a43ffaf3277`;
- liveness: `http://127.0.0.1:8088/api/health`;
- readiness: `http://127.0.0.1:8088/api/health/ready`.

The required legacy production baseline remains:

`4986a6d80460bd6d7681c70e09e61a15e31007f4`

## One-time legacy adoption

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

A later LIVE cutover still requires separate exact owner authorization bound to the final merged RPi5 source and exact CV release.
