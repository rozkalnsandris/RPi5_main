# V17 Hermes Tech rollback container retirement contract

## Status

**Production rollback-container retirement complete — 2026-08-07.**

V17 retired only the stopped legacy rollback container `hermes-blog-legacy-v14` after V16 proved that the authoritative Hermes Tech runtime survives a real RPi5 reboot under `hermes-tech-web.service` ownership.

Merging V17 performed no production mutation. The later explicit reviewed `apply` was the separately authorized production host cleanup action.

## Proven prerequisite

V16 real reboot-survival completed successfully on 2026-08-07:

- kernel boot ID changed from `8aaee2b2-e486-47ee-9d5e-56be15c03b00` to `7d742ff6-cd06-4010-a91e-797cbbd2fe5d`;
- `hermes-tech-web.service` entered active state approximately 18.1 seconds after boot;
- the live `hermes-blog` container was automatically recreated with a new container ID;
- exact loopback-only runtime invariants remained intact;
- direct LAN remained blocked;
- public Tech was HTTP 200 for three consecutive checks;
- Cloudflare recovered to HA readiness 4/4;
- `hermes-blog-legacy-v14` remained exited and did not participate in recovery.

## Critical image-retention boundary

The image

```text
sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa
```

is not a disposable rollback artifact.

The authoritative installed `hermes-tech-web.service` still uses that exact local image with `--pull=never` when creating `hermes-blog`. Removing or pruning the image would break a future service restart or host reboot.

V17 therefore preserved the exact image before, during and after rollback-container retirement.

## Reviewed operator

Authoritative operator:

```text
ops/bin/retire-hermes-tech-v14-rollback-container
```

It supports:

- `check` — default read-only validation;
- `apply` — explicit removal of only the exact stopped rollback container.

The only allowed Docker lifecycle mutation is:

```text
docker rm "$ROLLBACK"
```

where `$ROLLBACK` is exactly `hermes-blog-legacy-v14`.

`docker rm -f` is forbidden. The operator fails closed if the rollback container is running, missing in `check`, or has an unexpected container ID.

## Required pre-apply gates

Before removal, the operator must prove:

- installed `hermes-tech-web.service` matches the reviewed SHA256;
- the installed unit still contains `--pull=never` and the exact authoritative image ID;
- `hermes-tech-web.service` is active and enabled;
- live `hermes-blog` image is exact;
- Docker restart policy is `no`;
- publish is exactly `127.0.0.1:8089`;
- read-only content mount and JSON log-rotation contract remain intact;
- the authoritative image exists locally;
- V15 quarantine scripts and manifest remain present with audited checksums and mode `0400`;
- V16 protected reboot baseline remains present with metadata `root:root:600`;
- loopback origin is healthy;
- direct LAN `192.168.0.180:8089` remains blocked;
- UFW is active and contains no 8089 rule;
- public Tech is healthy;
- `cloudflared.service` is active and enabled with HA readiness 4/4;
- `hermes-blog-legacy-v14` is `exited` and has exact ID `5738272eb00eeffd518a9cb3cb236292a37f44bb360e5a4d703956ce82c50397`.

## Required post-apply gates

After the exact stopped container is removed, the operator must prove:

- `hermes-blog-legacy-v14` is absent;
- live `hermes-blog` container ID did not change during the operation;
- `cloudflared` PID did not change during the operation;
- the exact authoritative Nginx image still exists;
- `hermes-tech-web.service` remains active and enabled;
- exact loopback-only publish, mount and logging invariants remain intact;
- V15 quarantine and V16 reboot evidence remain intact;
- direct LAN remains blocked and UFW still has no 8089 rule;
- Cloudflare HA remains 4/4;
- public Tech returns HTTP 200 for three consecutive checks.

## Production completion evidence

The reviewed V17 `apply` completed successfully on production on 2026-08-07:

- exact repository main before apply: `8eaad466765f7caebdbfc06c382d3739949b5b84`;
- V17 regression and read-only preflight: PASS;
- rollback container before removal: `exited` with exact ID `5738272eb00eeffd518a9cb3cb236292a37f44bb360e5a4d703956ce82c50397`;
- operator marker: `HERMES_TECH_V14_ROLLBACK_CONTAINER_RETIREMENT_APPLY=PASS`;
- rollback container absent after apply: PASS;
- live `hermes-blog` container ID remained unchanged: `9dcf4dbb652aebded7c8454d4c17407573b5d6fa9569823308011551279a8073`;
- live and retained image remained exact: `sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa`;
- Docker publish remained exactly `127.0.0.1:8089`;
- Docker restart policy remained `no`;
- direct LAN `192.168.0.180:8089` remained blocked (`curl` rc 7);
- Cloudflare PID remained `878` and HA remained 4/4 during the operation;
- public Tech returned HTTP 200 for all three final checks;
- final wrapper marker: `HERMES_TECH_V17_ROLLBACK_CONTAINER_RETIREMENT=PASS`.

No image prune/removal, live-container lifecycle change, service restart, UFW/Cloudflare mutation, or V15/V16 evidence deletion occurred.

## Forbidden actions

V17 must not:

- stop, restart, recreate, rename or remove the live `hermes-blog` container;
- use `docker rm -f`;
- pull, remove, prune or retag the authoritative Nginx image;
- start, stop, restart, enable, disable, mask or edit systemd services;
- edit UFW;
- edit Cloudflare routes or Access;
- restore, modify or delete V15 quarantine evidence;
- delete or modify the V16 protected reboot baseline;
- alter Hermes Tech content, cron/timers or pull-deploy behavior;
- perform a host reboot.

## Production boundary

Repository merge was source-only. The explicit `apply` invocation was the separately confirmed production host cleanup action and is now complete.

No service/app deploy was required by V17. The authoritative Hermes Tech runtime and shared ingress remained running throughout the cleanup. The exact Nginx image remains an active boot-time dependency and must continue to be retained while `hermes-tech-web.service` references it with `--pull=never`.
