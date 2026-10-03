# Coloring Pages SIMPLE-DEPLOY target v1

Initial target issue: `#838`  
Media-store update issue: `#855`

This document records the source-owned RPi5 target contract for the Coloring Pages static UI.

## Consumer identity

- repository: `rozkalnsandris/coloring-pages`
- reviewed source: `dd9204581d46be618f1c7b0a6bafde90bcb691df`
- image: `ghcr.io/rozkalnsandris/coloring-pages`
- architecture: `linux/arm64`
- target alias: `coloring-pages-public-rpi5`
- shared SIMPLE-DEPLOY workflow revision: `94187cc447fc80757db10ac25d49717d00dc8430`

The reviewed importer-capable consumer publication produced immutable image `ghcr.io/rozkalnsandris/coloring-pages@sha256:5f61560cb674224052bc3ab8ca086c7997930027459f6c2648714d12c60af796`. The RPi5 deployer still resolves and verifies an exact immutable digest per deployment attempt; the mutable `:production` tag is discovery only.

## RPi5-owned adapter

- compose project: `coloring-pages-public`
- compose service: `coloring-pages`
- compose source: `ops/deploy/simple-deploy-compose/coloring-pages-public.yml`
- compose SHA-256: `77c71da44896b393002b7a13449d6fbaca76b38c6d982580d23156b674fe2941`
- loopback origin: `127.0.0.1:9191`
- liveness: `http://127.0.0.1:9191/health`
- readiness: `http://127.0.0.1:9191/ready`
- persistence: none
- pull profile: `public-anonymous-pull`

The adapter is read-only, uses `/tmp` tmpfs, `no-new-privileges`, and drops all Linux capabilities.

The consumer repository exposes only the stable persistence identity `coloring_pages_content`; it does not control an arbitrary RPi5 host path. This trusted adapter binds that identity to exactly `/srv/coloring-pages-content/public` and exposes it inside nginx only at `/var/lib/coloring-pages/public`. The bind is read-only and refuses automatic host-path creation. `inbox/`, `originals/`, and `state/` are outside the container surface.

## Importer operator

Issue #858 adds the RPi5-owned one-command production importer boundary:

- source: `ops/bin/coloring-pages-import`;
- installed path: `/usr/local/bin/coloring-pages-import`;
- machine contract: `ops/contracts/coloring-pages-importer-operator-v1.json`;
- installer source: `scripts/install-coloring-pages-importer-operator-v1.sh`;
- execution owner: `andris`, never root;
- immutable image: `ghcr.io/rozkalnsandris/coloring-pages@sha256:5f61560cb674224052bc3ab8ca086c7997930027459f6c2648714d12c60af796`;
- automatic image pull: forbidden;
- container network: none;
- root filesystem: read-only;
- content root: one exact read-write bind only for the one-off importer;
- production input: direct regular non-symlink PNG child of `/srv/coloring-pages-content/inbox`.

Installing the operator, making the immutable image available locally and running a production import are separate LIVE mutation classes. Source merge grants none of them.

## Port selection

The issue initially named `127.0.0.1:9190` as a candidate only.

A fresh read-only activation preflight on the trusted RPi5 found:

- `9190`: already listening and therefore rejected;
- `9191`: free at preflight time and selected for the reviewed source contract.

That observation is not durable LIVE proof. Any later cutover must revalidate the exact loopback port immediately before mutation and fail closed on drift.

## Authority boundary

Merging the source target does not install, start, replace, or restart any container or service.

A later LIVE cutover must separately freeze:

- exact reviewed RPi5_main SHA;
- exact target alias and Compose SHA-256;
- exact Coloring Pages source SHA;
- exact immutable `image@sha256` identity;
- existence and expected metadata of `/srv/coloring-pages-content/public`;
- exact read-only media-store bind semantics;
- fresh target/port baseline;
- allowed Docker mutation class;
- post-mutation verification and failure semantics.

Cloudflare, DNS, tunnel, firewall, protected configuration, secrets, credentials, persistent data and unrelated host control remain outside this target-registration lane.
