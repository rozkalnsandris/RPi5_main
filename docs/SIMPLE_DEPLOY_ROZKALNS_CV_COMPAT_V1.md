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

Fresh privileged metadata-only preflight later proved both fixed prerequisite destinations absent. Issue #808 simplifies the durable-data side without weakening the private-config boundary.

The fixed private runtime-config path must still exist **before** the first cutover mutation. It is not provisioned by the cutover. The legacy assistant intentionally migrated from DeepSeek to OpenAI Responses in consumer PR #429, so the legacy provider secret is not assumed compatible. The destination env contract pins public non-secret values `LLM_BASE_URL=https://api.openai.com` and `LLM_MODEL=gpt-5.6-luna`; `LLM_API_KEY` remains separately exact-gated secret material. Because the generic deployer runs as `rozkalns-simple-deployer`, the reviewed env metadata is root-owned, group-readable only by that runtime principal (`root:rozkalns-simple-deployer 0640`) under a non-world-readable traverse-only private parent (`0710`), so the deployer can reach the fixed file without directory-list access.

Durable data no longer needs a stale pre-cutover copy. The reviewed #808 helper resolves the fixed legacy source from passwd owner `andris` plus relative path `docker/cv/bot/data` and uses the fixed destination `/var/lib/rozkalns-simple-deployer/rozkalns-cv/data`; the home path is never caller-selectable. During the same one-time cutover, after all prechecks and exact-image pre-pull, the exact legacy `cvbot` writer is stopped; the helper then performs a byte-for-byte recursive copy through a fixed staging path and atomic publish. The helper does not stop/start/remove containers itself and does not query SQLite, migrate schema, transform DB content, print protected content, silently merge or overwrite an existing destination. Legacy and candidate `bot/storage.py` are byte-identical, so this is adoption only, not a schema migration. On the success path legacy `cvbot` is not restarted; the cutover immediately retires the remaining legacy containers and starts the exact new digest, preventing the adopted copy from becoming stale.

The cutover also quiesces the generic SIMPLE-DEPLOY timer before host registry/identity/Compose materialization, prestages the exact pinned image digest, observes `127.0.0.1:8088` unbound after legacy retirement, and then applies the reviewed generic target. Any post-mutation error remains fail-closed with no automatic retry, cleanup, rollback or alternate path.

Source acceptance of #802 therefore still does not authorize merge, private-config/data materialization, legacy runtime retirement, Docker/Compose execution, systemd mutation or LIVE activation.

## Authority boundary

Even after source registration is merged, separate exact owner authority remains required for:

1. private runtime configuration provisioning, including a valid OpenAI provider secret;
2. the composite one-time LIVE cutover authority that includes exact legacy `cvbot` stop, reviewed byte-copy data adoption, legacy retirement and SIMPLE-DEPLOY activation.

Ordinary SIMPLE-DEPLOY must not perform database/schema/data migration, recovery or cleanup, secret/permission mutation, Cloudflare/network mutation, private-provider activation or unrelated host control. Source merge runs no Docker/Compose command and grants no LIVE authority.
