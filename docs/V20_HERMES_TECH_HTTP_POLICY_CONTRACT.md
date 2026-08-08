# V20 Hermes Tech HTTP cache and security policy contract

## Status

**Reviewed source/CI gate only until separately authorized production activation.**

Merging V20 performs no production mutation.

V20 adds a source-controlled Nginx configuration for the existing Hermes Tech
static origin and updates the V14 systemd unit so the configuration is mounted
read-only into the existing pinned Nginx container. Installation, daemon reload,
container restart and public verification remain separate owner-authorized actions.

## Ownership boundary

Hermes Tech application source owns generated HTML/CSS/content and the expected
HTTP policy documented in `rozkalnsandris/hermes-tech`.

`RPi5_main` owns:

- `hermes-tech-web.service`;
- the `hermes-blog` container lifecycle;
- the root-owned installed Nginx policy file;
- host-level activation and rollback.

The shared `cloudflared.service` remains independently owned by `RPi5_main`.
V20 must not restart, replace, reconfigure or reconcile the shared connector.

## Preserved V14 runtime

V20 deliberately preserves all accepted V14 runtime identity:

- exact local Nginx image ID:
  `sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa`;
- Docker `--pull=never`;
- origin publish exactly `127.0.0.1:8089:80`;
- static content bind exactly
  `/home/andris/hermes-tech/site/public:/usr/share/nginx/html:ro`;
- Docker restart policy `no`;
- systemd restart policy `Restart=on-failure`;
- existing bounded JSON-file logging.

This is not an Nginx image upgrade.

## New root-owned configuration boundary

Reviewed source:

`ops/nginx/hermes-tech.conf`

Installed host target:

`/etc/rpi5-hermes-tech-nginx.conf`

The systemd unit mounts it read-only as:

`/etc/nginx/conf.d/default.conf`

The runtime must never bind the operator-writable Git checkout directly into the
container as Nginx configuration.

## Cache policy

The Nginx configuration uses one HTTP-scope `map` to select a cache policy and
one server-level `Cache-Control` header. This avoids relying on location-level
`add_header` inheritance behavior that differs across Nginx releases.

- default response policy: `Cache-Control: no-cache`;
- fingerprinted Hugo CSS matching `/css/site.min.<hex>.css`:
  `Cache-Control: public, max-age=31536000, immutable`.

Stable-name HTML, RSS/XML, robots.txt, llms.txt, web manifest and image URLs are
therefore not accidentally made immutable.

## Security policy

Every origin response must emit:

- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: strict-origin-when-cross-origin`;
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()`;
- the exact reviewed Content Security Policy from the Hermes Tech application
  contract, including `frame-ancestors 'none'`, `script-src 'none'`,
  `object-src 'none'`, self-hosted styles/images/manifest only, and no
  `unsafe-inline` or `unsafe-eval`.

V20 does not add HSTS at the loopback HTTP origin. Public TLS/HSTS behavior is an
edge concern and must not be guessed from the origin configuration.

## Static serving contract

The origin remains a static file server:

- root `/usr/share/nginx/html`;
- index `index.html`;
- `try_files $uri $uri/ =404`;
- no proxy/FastCGI/uWSGI/SCGI application runtime.

## Why V12 controlled deploy is not expanded

The V12 controlled deploy engine intentionally has an exact three-target scope
for backup runtime files. V14 systemd web runtime deployment was separately
reviewed and activated outside that target set. V20 keeps that boundary rather
than silently turning the backup deployment engine into a general service
manager.

Production V20 follows the established V14 exact-SHA install/cutover pattern.

## Required production preflight

Before any mutation, the owner must explicitly authorize a V20 production gate
and verify all of the following against the exact merged `RPi5_main` SHA:

1. local checkout is clean `main` and equals `origin/main`;
2. GitHub required checks for that exact SHA are successful;
3. reviewed Nginx config and unit SHA-256 values are recorded;
4. current installed V14 unit is backed up with ownership/mode/hash metadata;
5. current `hermes-tech-web.service` is active and enabled;
6. current `hermes-blog` uses the exact retained image and loopback-only publish;
7. exact retained image exists locally; no image pull is permitted;
8. current loopback and public site return HTTP 200;
9. `cloudflared.service` PID/readiness is recorded before the gate.

The reviewed Nginx config must be syntax-tested against the exact retained local
image before the active service is replaced.

## Install-only gate

After the preflight and only with explicit authorization:

1. install `ops/nginx/hermes-tech.conf` as
   `/etc/rpi5-hermes-tech-nginx.conf`, owner `root:root`, mode `0644`;
2. verify installed SHA-256 equals the reviewed source SHA-256;
3. install `ops/systemd/hermes-tech-web.service` as
   `/etc/systemd/system/hermes-tech-web.service`, owner `root:root`, mode `0644`;
4. verify installed SHA-256 equals the reviewed source SHA-256;
5. run `systemd-analyze verify` against the installed unit;
6. run `systemctl daemon-reload`;
7. do **not** restart the service yet;
8. verify current loopback/public serving remains healthy and the existing
   container identity is unchanged.

This separates file installation from runtime cutover.

## Runtime canary gate

A separately confirmed runtime canary may then restart only
`hermes-tech-web.service`.

Post-start requirements:

- service active and enabled;
- container `hermes-blog` uses the exact retained image;
- Docker restart policy remains `no`;
- publish remains exactly `127.0.0.1:8089:80`;
- public content bind remains read-only;
- Nginx config bind is exactly `/etc/rpi5-hermes-tech-nginx.conf` to
  `/etc/nginx/conf.d/default.conf`, read-only;
- direct LAN access on 8089 remains blocked;
- loopback and public home/article/RSS requests return HTTP 200;
- fingerprinted CSS returns the immutable cache policy;
- HTML, RSS, robots.txt, llms.txt and manifest return `Cache-Control: no-cache`;
- all required security headers match the reviewed policy exactly;
- there are no duplicate/conflicting Cache-Control or security header values;
- shared `cloudflared.service` PID/readiness is unchanged.

## Rollback

Before install, retain the exact previous installed unit and metadata. The prior
V14 unit does not require `/etc/rpi5-hermes-tech-nginx.conf`.

On any install or runtime verification failure:

1. stop the attempted V20 service instance if necessary;
2. restore the previous V14 unit atomically with original ownership/mode;
3. `systemctl daemon-reload`;
4. start/enable the restored `hermes-tech-web.service`;
5. require loopback and public Tech HTTP 200;
6. verify exact retained image and loopback-only publish;
7. verify `cloudflared.service` PID/readiness remains unchanged;
8. only after successful rollback verification may the new root-owned Nginx
   config be removed or retained as inactive evidence.

The stopped legacy V14 rollback container/image policy remains governed by the
existing V14 contract; V20 does not prune rollback assets.

## Non-goals

V20 does not:

- upgrade Nginx;
- change Cloudflare routes, credentials or Access policy;
- change UFW;
- change Hermes Tech Hugo/content generation;
- change collector/digest scheduling;
- change the generic V12 backup deploy target set;
- authorize production installation or restart by being merged.
