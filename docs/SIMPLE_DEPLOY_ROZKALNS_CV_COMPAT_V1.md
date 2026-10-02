# rozkalns-cv SIMPLE-DEPLOY compatibility and first adoption v1

Status: **source-ready only; LIVE remains separately owner-gated**  
Current simplification: `RPi5_main#821`

## Operator model

After the one-time legacy adoption, the normal delivery path is intentionally small:

`consumer merge → SIMPLE-DEPLOY → production`

SIMPLE-DEPLOY already owns the technical host reconciliation: resolve the immutable production digest, pull it, run `docker compose up -d --wait`, verify the running image identity, liveness/readiness and write the deployment receipt. There is no separate owner-facing “RPi5 reconcile” phase.

## Docker Compose basis

The RPi5-owned production adapter follows Docker Compose's ordinary host-path model:

- `env_file` supplies container environment variables from an external file;
- the existing private env is reused directly at `/home/andris/docker/cv/bot/.env`;
- the existing durable data directory is bind-mounted directly from `/home/andris/docker/cv/bot/data`;
- the bind uses long syntax with `create_host_path: false`, so a missing source fails instead of silently creating an empty directory;
- absolute paths are deliberate because this is a host-owned RPi5 production adapter, not a portable developer Compose file;
- public non-secret provider literals are overridden in Compose as `LLM_BASE_URL=https://api.openai.com` and `LLM_MODEL=gpt-5.6-luna`; secret values remain external.

Official Docker references:

- https://docs.docker.com/reference/compose-file/services/
- https://docs.docker.com/reference/cli/docker/compose/up/

## Current exact release

- consumer: `rozkalnsandris/rozkalns-cv`;
- source: `d75863d0ce4cfdac0015150137523abbaccf5914`;
- immutable image digest: `sha256:ba9e24c82eccd833cfe42d6a4aa61ef76c584bcfd4c27efbced13c3a408d2a1a`;
- shared SIMPLE-DEPLOY workflow: `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- target: `rozkalns-cv-rpi5`;
- RPi5 Compose SHA-256: `33174cd778df2c1e4012735c5b01ba4af2d6873ec14f3f1ade985f2f2d62b7f0`;
- liveness: `http://127.0.0.1:8088/api/health`;
- readiness: `http://127.0.0.1:8088/api/health/ready`.

The legacy production baseline for the first adoption remains `4986a6d80460bd6d7681c70e09e61a15e31007f4`.

## Existing state is reused, not migrated

The legacy and current candidate `bot/storage.py` Git blob is identical:

`7a7ce05021223b43686cd93513208bb0a249d9bc`

Both legacy and SIMPLE-DEPLOY application runtimes use UID/GID `10001:10001`.

Therefore the first adoption does not create a second data tree, copy the SQLite database, run a schema migration or change ownership. The existing data directory is mounted in place.

Likewise, SIMPLE-DEPLOY does not create a second private env file. It reuses the existing host file. Source work and cutover preflight may validate only path metadata; they do not read, print, copy or rewrite secret contents.

## One-time legacy adoption

The one-time cutover remains a single STRICT LIVE operation because the old `cv` and `cvbot` containers already own the production runtime.

Internally it performs only the technical transition needed to reach the steady state:

1. revalidate exact source/digest, current production pointer, legacy baseline and existing env/data path metadata;
2. quiesce the generic SIMPLE-DEPLOY timer while its target registry/Compose binding is installed;
3. retire the exact legacy `cvbot` and `cv` containers;
4. prove `127.0.0.1:8088` is unbound;
5. invoke the normal generic SIMPLE-DEPLOY target for the exact immutable digest;
6. require receipt identity plus liveness/readiness HTTP 200 and the public UI v2 marker;
7. resume the generic timer only after success.

These are implementation details of the one-time adoption, not recurring owner gates.

After success, future CV releases use the ordinary SIMPLE-DEPLOY path only.

## Failure and authority boundary

The cutover is fail-closed after the first mutation: no automatic retry, cleanup, rollback or alternate deployment path.

Source merge does not authorize the one-time LIVE cutover. This source lane also does not authorize:

- secret/env content reads or writes;
- persistent-data copy, migration, reownership, deletion or inspection;
- database queries/schema/data migration;
- unrelated Docker/systemd/filesystem mutation;
- Cloudflare/network changes;
- repository settings/permissions/secrets changes.

Any LIVE execution still requires a separate exact owner authorization bound to the final merged RPi5 source and exact CV release.
