# Coloring Pages SIMPLE-DEPLOY target v1

Issue: `#838`

This document records the source-owned RPi5 target contract for the Coloring Pages static UI.

## Consumer identity

- repository: `rozkalnsandris/coloring-pages`
- reviewed source: `dd9204581d46be618f1c7b0a6bafde90bcb691df`
- image: `ghcr.io/rozkalnsandris/coloring-pages`
- architecture: `linux/arm64`
- target alias: `coloring-pages-public-rpi5`
- shared SIMPLE-DEPLOY workflow revision: `94187cc447fc80757db10ac25d49717d00dc8430`

The reviewed consumer publication produced an immutable image digest before this source registration lane. The RPi5 deployer still resolves and verifies an exact immutable digest per deployment attempt; the mutable `:production` tag is discovery only.

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
- fresh target/port baseline;
- allowed Docker mutation class;
- post-mutation verification and failure semantics.

Cloudflare, DNS, tunnel, firewall, protected configuration, secrets, credentials, persistent data and unrelated host control remain outside this target-registration lane.
