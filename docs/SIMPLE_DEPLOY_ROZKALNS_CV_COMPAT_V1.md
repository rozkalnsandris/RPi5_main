# rozkalns-cv SIMPLE-DEPLOY compatibility prerequisite v1

Status: source-only prerequisite; target registration remains pending.

## Accepted consumer evidence

- consumer repository: `rozkalnsandris/rozkalns-cv`
- accepted SIMPLE-DEPLOY contract revision: `139fb7046c77e1e58ec4a0876db3dddb96c85cb5`
- target alias: `rozkalns-cv-rpi5`
- image: `ghcr.io/rozkalnsandris/rozkalns-cv`
- shared workflow: `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`
- architecture: `linux/arm64`
- liveness: `/api/health`
- readiness: `/api/health/ready`

The consumer contract is not stateless. Its Compose source uses a private environment file and a persistent bind for `/app/data`, while the manifest's named-volume list is empty. The application stores durable SQLite state beneath `/app/data` and can initialize or maintain that database as part of normal application startup/runtime behavior. That boundary must not be converted into an implicit data/config migration by target registration.

## RPi5-owned adapter

`ops/deploy/simple-deploy-compose/rozkalns-cv.yml` freezes the host-facing surface:

- loopback-only `127.0.0.1:8088:8080`;
- fixed private environment path `/etc/rozkalns-simple-deployer/private/rozkalns-cv.env`;
- fixed existing-data bind `/var/lib/rozkalns-simple-deployer/rozkalns-cv/data` with `create_host_path: false`;
- non-root `10001:10001`, read-only root filesystem, bounded tmpfs, `no-new-privileges`, `cap_drop: ALL` and bounded PID count;
- `:production` only as discovery/default metadata; the generic deployer must freeze an exact image digest before mutation;
- fixed readiness healthcheck on the combined CV runtime.

The adapter intentionally removes consumer-relative `${...}` host paths and does not inherit the consumer's fixed custom bridge subnet/static container IP as host authority.

## Authority boundary

Merging this prerequisite does **not** add `rozkalns-cv-rpi5` to `ops/deploy/simple-deploy-targets-v1.json` and does not install or start anything.

A follow-up tracked source change is required to register the target. Even after registration is merged, separate exact owner authority remains required for:

1. private runtime configuration provisioning;
2. adoption/materialization of persistent CV data;
3. retirement/replacement of the existing CV runtime;
4. the one-time SIMPLE-DEPLOY target installation/cutover.

Ordinary SIMPLE-DEPLOY must not perform database/schema/data migration, recovery or cleanup, secret/permission mutation, Cloudflare/network mutation, private-provider activation or unrelated host control. Source merge runs no Docker/Compose command and grants no LIVE authority.
