# Coloring Pages SIMPLE-DEPLOY target v1

Initial target issue: `#838`  
Media-store update issue: `#855`  
Importer-operator issue: `#858`  
Installed-target reconciliation issue: `#860`

This document records the source-owned RPi5 target contract for the Coloring Pages static UI and importer boundary.

## Consumer identity

- repository: `rozkalnsandris/coloring-pages`
- reviewed media-store consumer source: `eaeed0c8f3d973dc938892abdd69d12437ac049e`
- reviewed importer-capable consumer source: `ab8f874f681fb2adb6f18f4a7c8066b44ace443b`
- image: `ghcr.io/rozkalnsandris/coloring-pages`
- reviewed importer-capable image: `ghcr.io/rozkalnsandris/coloring-pages@sha256:5f61560cb674224052bc3ab8ca086c7997930027459f6c2648714d12c60af796`
- architecture: `linux/arm64`
- target alias: `coloring-pages-public-rpi5`
- shared SIMPLE-DEPLOY workflow revision: `94187cc447fc80757db10ac25d49717d00dc8430`

The RPi5 deployer resolves and verifies an exact immutable digest per deployment attempt. The mutable `:production` tag is discovery only and never owner authority.

## RPi5-owned adapter

- compose project: `coloring-pages-public`
- compose service: `coloring-pages`
- compose source: `ops/deploy/simple-deploy-compose/coloring-pages-public.yml`
- reviewed compose SHA-256: `142c30bdd1080de90360f287e5b6fae27611c535caef0a41a09a998528bcbbc2`
- loopback origin: `127.0.0.1:9191`
- liveness: `http://127.0.0.1:9191/health`
- readiness: `http://127.0.0.1:9191/ready`
- persistence identity: `coloring_pages_content`
- trusted host source: `/srv/coloring-pages-content/public`
- container target: `/var/lib/coloring-pages/public`
- mount mode: read-only
- host-path auto-create: forbidden
- pull profile: `public-anonymous-pull`

The adapter is read-only, uses `/tmp` tmpfs, `no-new-privileges`, and drops all Linux capabilities. Only `public/` is exposed to the long-running web container; `inbox/`, `originals/`, and `state/` remain outside that surface.

## Importer operator

Issue #858 adds the RPi5-owned one-command production importer boundary:

- source: `ops/bin/coloring-pages-import`
- installed path: `/usr/local/bin/coloring-pages-import`
- machine contract: `ops/contracts/coloring-pages-importer-operator-v1.json`
- installer source: `scripts/install-coloring-pages-importer-operator-v1.sh`
- execution owner: `andris`, never root
- immutable image: `ghcr.io/rozkalnsandris/coloring-pages@sha256:5f61560cb674224052bc3ab8ca086c7997930027459f6c2648714d12c60af796`
- automatic image pull: forbidden
- container network: none
- root filesystem: read-only
- content root: one exact read-write bind only for the one-off importer
- production input: direct regular non-symlink PNG child of `/srv/coloring-pages-content/inbox`

Installing the operator, making the immutable image available locally and running a production import are separate LIVE mutation classes. Source merge grants none of them.

## Installed-target reconciliation

The trusted host installation predates the media-store target source and therefore must not be upgraded by overloading the first-install-only installer.

Issue #860 defines a dedicated reconciliation contract:

```text
ops/contracts/simple-deploy-coloring-pages-reconciliation-v1.json
scripts/reconcile-simple-deploy-coloring-pages-v1.py
```

Fresh baseline bound by that contract:

- installed registry SHA-256: `46667f60470d032cd60f356d1fcc32596c75d6dfc38f9d9539531768733c8e6c`
- installed identity SHA-256: `68be71f09292496bd4ff5dbe8f322804df59065bc41cfa52bdb5a72ddc99e3a2`
- installed Coloring Pages Compose SHA-256: `77c71da44896b393002b7a13449d6fbaca76b38c6d982580d23156b674fe2941`
- desired registry SHA-256: `e68fb9d674dbc044454563c8c8ba74c757c958ea78ff980dd0003b64d7e7bd7d`
- desired Coloring Pages Compose SHA-256: `142c30bdd1080de90360f287e5b6fae27611c535caef0a41a09a998528bcbbc2`

The reconciler can replace only:

1. `/etc/rozkalns-simple-deployer/compose/coloring-pages-public.yml`
2. `/etc/rozkalns-simple-deployer/targets.json`
3. `/etc/rozkalns-simple-deployer/identity.json`

All three desired files are staged on the same filesystem before installed-file replacement. Compose is replaced first, registry second, and identity last as the source-provenance marker. Baseline drift or source drift fails before mutation.

After the first mutation, any error or ambiguity is fail-closed: no automatic retry, cleanup, rollback or alternate mutation path.

## Port selection

The original issue named `127.0.0.1:9190` as a candidate only.

A read-only activation preflight selected `127.0.0.1:9191`. This is not durable LIVE proof; any later cutover must revalidate the exact loopback port and current owner immediately before Docker mutation.

## Authority boundary

Merging source does not reconcile installed files, install the importer wrapper, pull an image, deploy/restart a container or import production content.

A later composite LIVE gate must separately bind:

- exact reviewed `RPi5_main` SHA
- exact reconciliation baseline and three-file mutation
- exact target alias and Compose SHA-256
- exact Coloring Pages consumer source SHA
- exact immutable `image@sha256` identity
- exact content-store metadata
- fresh target/port/container baseline
- exact importer-wrapper installation mutation if included
- allowed Docker mutation class
- verification and fail-closed semantics

Production content import remains a separate application-data mutation and is not implied by target reconciliation or application deployment.

Cloudflare, DNS, tunnel, firewall, secrets, credentials, unrelated permissions and unrelated host control remain outside this lane.
