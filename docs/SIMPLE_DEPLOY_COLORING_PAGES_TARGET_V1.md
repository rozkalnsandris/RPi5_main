# Coloring Pages SIMPLE-DEPLOY target v1

Initial target issue: `#838`  
Media-store update issue: `#855`  
Installed-target alignment issue: `#860`

## Consumer identity

- repository: `rozkalnsandris/coloring-pages`
- media-store source: `eaeed0c8f3d973dc938892abdd69d12437ac049e`
- publish/import image: `ghcr.io/rozkalnsandris/coloring-pages@sha256:1e6ceaeb9cc84164aef8f4680cee6ee9b4b9a3094e59c6026f590e58a3c043e8`
- target alias: `coloring-pages-public-rpi5`
- architecture: `linux/arm64`
- shared SIMPLE-DEPLOY revision: `94187cc447fc80757db10ac25d49717d00dc8430`

The mutable `:production` tag is discovery only. Deployment and content-import authority bind immutable image digests.

## RPi5 adapter

- compose project/service: `coloring-pages-public/coloring-pages`
- compose source: `ops/deploy/simple-deploy-compose/coloring-pages-public.yml`
- compose SHA-256: `142c30bdd1080de90360f287e5b6fae27611c535caef0a41a09a998528bcbbc2`
- origin: `127.0.0.1:9191`
- liveness: `http://127.0.0.1:9191/health`
- readiness: `http://127.0.0.1:9191/ready`
- persistence identity: `coloring_pages_content`
- host source: `/srv/coloring-pages-content/public`
- container target: `/var/lib/coloring-pages/public`
- mount: read-only, `create_host_path: false`
- pull profile: `public-anonymous-pull`

Only `public/` is visible to the long-running nginx container. `inbox/`, `originals/` and `state/` remain outside it.

## One content publish operator

Coloring Pages uses one host command for Drive ingestion and import:

- source: `ops/bin/coloring-pages-drive-ingest`
- installed path: `/usr/local/bin/coloring-pages-drive-ingest`
- contract: `ops/contracts/coloring-pages-drive-ingest-operator-v1.json`
- installer: `scripts/install-coloring-pages-drive-ingest-operator-v1.sh`
- execution owner: `andris`, never root
- Drive access: read-only
- importer: exact immutable image digest above
- automatic image pull: forbidden
- importer network: none
- importer root filesystem: read-only
- one exact RW bind: `/srv/coloring-pages-content`

There is no separate host `coloring-pages-import` wrapper. This removes wrapper-to-wrapper Git blob coupling while preserving the immutable importer image and the existing content safety checks.

Operator installation and production content publication remain separate LIVE mutation classes.

## Installed-target alignment

The host SIMPLE-DEPLOY files predate the media-store adapter. The first-install installer stays first-install-only.

Issue #860 therefore uses one small fixed helper:

```text
scripts/align-simple-deploy-coloring-pages-v1.py
ops/contracts/simple-deploy-coloring-pages-alignment-v1.json
```

It accepts only `--expected-source-sha` and `--apply`. It can replace exactly three files:

1. `/etc/rozkalns-simple-deployer/compose/coloring-pages-public.yml`
2. `/etc/rozkalns-simple-deployer/targets.json`
3. `/etc/rozkalns-simple-deployer/identity.json`

Before mutation it requires the reviewed LIVE baseline hashes:

- registry: `46667f60470d032cd60f356d1fcc32596c75d6dfc38f9d9539531768733c8e6c`
- identity: `68be71f09292496bd4ff5dbe8f322804df59065bc41cfa52bdb5a72ddc99e3a2`
- Coloring Pages Compose: `77c71da44896b393002b7a13449d6fbaca76b38c6d982580d23156b674fe2941`

Desired source is fixed to:

- registry: `88c3acbf304ab9676a6a767e5f3055351f20fd88ca9bf1bf4a2cb1210ef3617f`
- Coloring Pages Compose: `142c30bdd1080de90360f287e5b6fae27611c535caef0a41a09a998528bcbbc2`
- identity source SHA: the exact owner-authorized `RPi5_main` SHA

All three files are staged before replacement. Compose is replaced first, registry second, identity last. Any baseline/source drift fails before mutation. After mutation starts there is no automatic retry, cleanup or rollback.

## Authority boundary

Source merge does not align installed files, install/update the publish operator, execute Docker/rclone, or import production content.

A later LIVE gate must bind the exact reviewed `RPi5_main` SHA, current host baseline and the exact content publication identity when content is published.

Cloudflare, DNS, tunnel, firewall, secrets, credentials and unrelated host control stay outside this lane.
