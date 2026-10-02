# rozkalns-cv SIMPLE-DEPLOY compatibility and target registration v1

Status: source compatibility accepted; static RPi5 target registered; deterministic one-time cutover source contract tracked by #802; LIVE remains separately gated.

## Accepted consumer evidence

- consumer repository: `rozkalnsandris/rozkalns-cv`
- accepted SIMPLE-DEPLOY contract revision: `139fb7046c77e1e58ec4a0876db3dddb96c85cb5`
- target alias: `rozkalns-cv-rpi5`
- image: `ghcr.io/rozkalnsandris/rozkalns-cv`
- shared workflow: `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`
- architecture: `linux/arm64`
- liveness: `/api/health`
- readiness: `/api/health/ready`

The consumer contract is not stateless. Its Compose source uses a private environment file and a persistent bind for `/app/data`, while the manifest's named-volume list is empty. The application stores durable SQLite state beneath `/app/data` and can initialize or maintain that database as part of normal application startup/runtime behavior. Target registration must not convert that boundary into an implicit data/config migration.

## RPi5-owned adapter

`ops/deploy/simple-deploy-compose/rozkalns-cv.yml` freezes the host-facing surface:

- loopback-only `127.0.0.1:8088:8080`;
- fixed private environment path `/etc/rozkalns-simple-deployer/private/rozkalns-cv.env`;
- fixed existing-data bind `/var/lib/rozkalns-simple-deployer/rozkalns-cv/data` with `create_host_path: false`;
- non-root `10001:10001`, read-only root filesystem, bounded tmpfs, `no-new-privileges`, `cap_drop: ALL` and bounded PID count;
- `:production` only as discovery/default metadata; the generic deployer must freeze an exact image digest before mutation;
- fixed readiness healthcheck on the combined CV runtime.

The adapter intentionally removes consumer-relative `${...}` host paths and does not inherit the consumer's fixed custom bridge subnet/static container IP as host authority.

## Static target registration

The follow-up source change after PR #741 registers `rozkalns-cv-rpi5` in `ops/deploy/simple-deploy-targets-v1.json` and records it in `ops/contracts/simple-deploy-host-v1.json`.

The registry intentionally keeps `persistent_volumes` empty because the consumer manifest declares no named volumes. Durable CV state remains represented by the fixed existing-data bind in the RPi5-owned Compose adapter, with `create_host_path: false`; registration therefore cannot create, initialize, migrate or adopt that data path.

Registration is source metadata only. It does not install the target, provision private runtime configuration, materialize/adopt persistent data, retire the existing CV runtime, or run Docker/Compose.


## Selected one-time cutover source contract (#802)

The selected source lane now freezes a deterministic first activation for `rozkalns-cv-rpi5` without granting LIVE authority:

- candidate CV source: `645717e63596a6ece415d9f4ef69367b9e6ecafc`;
- successful SIMPLE-DEPLOY publication run: `36241004385`;
- immutable candidate digest: `sha256:bc6cb2ab3c0e944db49b6c403212802d5289eabaf77db4dd30082856a9fdaadc`;
- observed legacy production source baseline: `4986a6d80460bd6d7681c70e09e61a15e31007f4`;
- cutover contract: `ops/deploy/rozkalns-cv-simple-deploy-cutover-v1.json`;
- host activation registry: `ops/deploy/baselines/simple-deploy-targets-weather-cv-v1.json`.

The activation registry intentionally contains **only Weather + CV**. It must not copy the full reviewed four-target source registry into the host, because Hermes Tech and Hermes Deals are source-registered but not activated by the CV decision.

The one-time cutover requires the fixed private runtime-config path and fixed persistent-data path to exist **before** the first cutover mutation. The cutover contract neither reads/provisions protected config nor creates/adopts/copies/migrates persistent data. If either prerequisite is absent, that prerequisite remains a separate exact owner-authorized operation.

The cutover also quiesces the generic SIMPLE-DEPLOY timer before host registry/identity/Compose materialization, prestages the exact pinned image digest, retires only the fixed legacy `cv` and `cvbot` application containers, observes `127.0.0.1:8088` unbound, and then applies the reviewed generic target. Any post-mutation error remains fail-closed with no automatic retry, cleanup, rollback or alternate path.

Source acceptance of #802 therefore still does not authorize merge, private-config/data materialization, legacy runtime retirement, Docker/Compose execution, systemd mutation or LIVE activation.

## Authority boundary

Even after source registration is merged, separate exact owner authority remains required for:

1. private runtime configuration provisioning;
2. adoption/materialization of persistent CV data;
3. retirement/replacement of the existing CV runtime;
4. the one-time SIMPLE-DEPLOY target installation/cutover.

Ordinary SIMPLE-DEPLOY must not perform database/schema/data migration, recovery or cleanup, secret/permission mutation, Cloudflare/network mutation, private-provider activation or unrelated host control. Source merge runs no Docker/Compose command and grants no LIVE authority.
