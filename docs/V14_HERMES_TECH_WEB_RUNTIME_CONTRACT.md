# V14 Hermes Tech static web runtime contract

## Status

**Source reviewed in Git; production migration pending.**

This contract moves the legacy standalone `hermes-blog` Docker container into
reviewed host infrastructure ownership and narrows the Hermes Tech origin from a
wildcard Docker publish to loopback-only host access.

Merging V14 performs no production mutation. It does not install or enable the
unit, stop or replace the existing container, change the Cloudflare route, edit
UFW, update the Nginx image, change Hermes Tech content generation, or restart
the shared Cloudflare connector.

## Ownership boundary

Hermes Tech application deployment owns content generation and publication files only.
It may update `/home/andris/hermes-tech/site/public` and verify the public site,
but it does not own the static web container lifecycle.

`RPi5_main` owns the `hermes-blog` container lifecycle.

The shared `cloudflared.service` remains separately owned by `RPi5_main` under
the V13 contract. Neither the Hermes Tech application deploy nor this static-web
runtime may start, stop, replace, reconcile, roll back or hold credentials for
the shared Cloudflare Tunnel connector.

## Verified pre-migration runtime

The live read-only audit on 2026-08-07 established:

- container name: `hermes-blog`;
- image originally named `nginx:alpine`;
- running immutable image ID:
  `sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa`;
- the running image has no repository tags and no repository digests available;
- image architecture: `arm64`;
- image creation timestamp: `2026-06-22T20:53:00.395943424Z`;
- network mode: Docker default bridge;
- container restart policy: `unless-stopped`;
- host publish: wildcard host port `8089` to container port `80`;
- static content bind:
  `/home/andris/hermes-tech/site/public:/usr/share/nginx/html:ro`;
- JSON-file logging: `max-size=10m`, `max-file=3`;
- loopback origin: HTTP 200;
- direct LAN origin: HTTP 200;
- public `https://tech.rozkalns.net/`: HTTP 200;
- shared Cloudflare connector remained on the established host systemd PID during
  the audit.

The Hermes Tech pull-deploy systemd timer updates the application checkout and
published static files. It does not create, replace or supervise `hermes-blog`.

## Image identity policy

The mutable `nginx:alpine` tag currently resolves to an image different from the
one used by the running production container. The running image has no
`RepoDigest`, so this migration cannot pin a registry digest for the exact live
bytes.

To keep network/lifecycle hardening separate from an Nginx upgrade, V14 pins the
exact local image ID:

```text
sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa
```

The reviewed service uses `--pull=never`. Production apply must prove that this
exact image exists locally before the legacy container is stopped. The image
must not be pruned until V14 migration and rollback observation are complete.

A later Nginx image refresh is a separate reviewed change with a registry digest,
compatibility check, public-site verification and rollback image retained.

## Reviewed systemd source

Authoritative source:

```text
ops/systemd/hermes-tech-web.service
```

Installed target after explicit production apply:

```text
/etc/systemd/system/hermes-tech-web.service
```

The unit requires Docker and the published-content directory, creates a container
from the exact retained local image, starts it attached so systemd observes its
lifetime, and removes the stopped container after service shutdown.

Docker restart policy is explicitly `no`; systemd uses `Restart=on-failure`.
Docker and systemd restart supervision must not be combined.

The unit deliberately does not use force-removal in `ExecStartPre` or
`ExecStopPost`. Accidentally starting the unit while a running legacy
`hermes-blog` still exists must fail safely because of the name conflict rather
than destroy the working container.

## Final origin contract

The final Docker publish is exactly:

```text
127.0.0.1:8089:80
```

The final Cloudflare origin for `tech.rozkalns.net` is:

```text
http://127.0.0.1:8089
```

After migration:

- `curl http://127.0.0.1:8089/` must succeed;
- direct `http://192.168.0.180:8089/` must fail;
- `https://tech.rozkalns.net/` must remain HTTP 200;
- Docker inspection must show only loopback host binding for container port 80;
- wildcard IPv4, wildcard IPv6 and LAN-specific 8089 publishes are forbidden.

The Cloudflare route is changed before the container migration because the
existing wildcard listener already accepts loopback traffic. That lets the route
change itself be proven independently while the legacy runtime remains intact.

## Static content and logging contract

V14 preserves the verified application-data boundary:

```text
/home/andris/hermes-tech/site/public
    -> /usr/share/nginx/html
    read-only
```

The migration does not change Hugo output, cron schedules, pull-deploy behavior,
Nginx configuration, application content, container root filesystem mode,
container capabilities, memory limits or CPU limits.

The existing bounded Docker JSON logging policy is preserved:

```text
max-size=10m
max-file=3
```

## Production migration gates

Production apply is a separate, explicitly confirmed transaction after merge.
The order is:

1. require exact merged `main` and successful GitHub checks;
2. prove `cloudflared.service` active/enabled with the expected unchanged PID and
   four active edge connections;
3. prove current loopback, LAN and public Hermes Tech HTTP health;
4. prove the exact retained image ID exists locally;
5. prove the tracked unit is byte-identical to the intended installed source;
6. install the reviewed unit without enabling or starting it;
7. run `systemd-analyze verify` on the installed unit;
8. change only the Cloudflare `tech.rozkalns.net` origin from
   `http://192.168.0.180:8089` to `http://127.0.0.1:8089`;
9. while the legacy wildcard container still runs, require public Tech HTTP 200,
   loopback HTTP 200 and unchanged Cloudflare connector readiness;
10. stop and remove only the legacy `hermes-blog` container;
11. start and enable `hermes-tech-web.service` immediately;
12. require service active/enabled and container running from the exact image ID;
13. require Docker port binding exactly `127.0.0.1:8089 -> 80/tcp`;
14. require loopback HTTP 200 and public Tech HTTP 200;
15. require direct LAN 8089 to fail;
16. require the shared Cloudflare connector PID and four-edge readiness to remain
    unchanged;
17. only after those gates pass, remove the obsolete UFW LAN `8089/tcp` allow
    rule by matching its current specification/number rather than assuming an
    old rule number;
18. repeat loopback, public, direct-LAN-failure and Cloudflare readiness checks;
19. quarantine or remove legacy host-local setup scripts that could recreate the
    wildcard container only in a separate cleanup step after observation.

The container cutover itself cannot run two listeners on the same host port at
the same time. The route is therefore pre-proven on loopback and the old
container stop/new service start are performed as one tightly bounded operation.

## Rollback

Before removing the UFW LAN rule, rollback is:

1. stop `hermes-tech-web.service`;
2. remove any stopped reviewed `hermes-blog` container if necessary;
3. recreate the legacy runtime from the retained exact image ID with the verified
   original read-only content bind, JSON logging and wildcard 8089 publish;
4. require loopback and public Tech HTTP 200;
5. if required, restore the Cloudflare origin to
   `http://192.168.0.180:8089` only after the legacy listener is healthy;
6. verify the shared Cloudflare connector remains healthy.

The retained image ID is a required rollback asset until the migration is closed.
Image pruning is forbidden during that period.

After the loopback runtime is accepted and the LAN UFW rule is removed, rollback
must restore both the legacy listener and any required LAN firewall rule before a
LAN-origin route is restored.

## Exclusions

V14 does not:

- update Nginx;
- introduce Docker Compose for Hermes Tech;
- change Hugo or content generation;
- change Hermes Tech collector/digest cron schedules;
- change the pull-deploy timer;
- change Cloudflare credentials or Access policy;
- restart or replace `cloudflared.service`;
- change any other application origin or UFW rule;
- delete legacy scripts during the initial runtime cutover.
