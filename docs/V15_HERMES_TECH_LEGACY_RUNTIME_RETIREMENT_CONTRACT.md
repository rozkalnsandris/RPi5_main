# V15 Hermes Tech legacy runtime retirement contract

## Status

**Production host quarantine complete — 2026-08-07.**

V15 retires only legacy host-local scripts that can recreate or destructively replace the pre-V14 `hermes-blog` runtime. It does not alter the authoritative Hermes Tech runtime, Cloudflare route, UFW, application content, schedules, Nginx image, or the retained rollback container.

## Authoritative runtime

The accepted production state from V14 remains unchanged:

- `hermes-tech-web.service` active and enabled;
- Docker publish exactly `127.0.0.1:8089:80`;
- exact retained image `sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa`;
- Docker restart policy `no`, systemd as the only supervisor;
- `tech.rozkalns.net` origin `http://127.0.0.1:8089`;
- no LAN UFW allow rule for 8089;
- stopped rollback container `hermes-blog-legacy-v14` retained separately.

## Read-only audit result

The 2026-08-07 host audit produced seven grep candidates. Five are intentional/current or inert text and must not be quarantined:

- `/etc/systemd/system/hermes-tech-web.service`;
- `/home/andris/RPi5_main/ops/systemd/hermes-tech-web.service`;
- `/home/andris/RPi5_main/tests/test-hermes-tech-web-runtime.sh`;
- `/home/andris/RPi5_main/docs/V14_HERMES_TECH_WEB_RUNTIME_CONTRACT.md`;
- `/home/andris/.hermes/state/rich_sent_index.json`.

Only two files are mutation-capable legacy launch scripts:

1. `/home/andris/hermes-tech-phase3/setup3.sh`
   - SHA256 `7a1455e938354871b46a91dc00bccb6679ad5c2799f1368e7d5b829190604226`;
   - contains a historical `docker run --name hermes-blog --restart unless-stopped` path with wildcard host publication.
2. `/home/andris/_home_cleanup_20260804-221307/fix-port.sh`
   - SHA256 `115566b8f432863370bd4945f960a8f587f8041df7512bb81174388d42210c98`;
   - can force-remove `hermes-blog`, recreate it, and publish `8089:80` broadly.

Neither exact path is referenced by current systemd or cron scheduling.

## Reviewed operator

Authoritative one-time operator:

```text
ops/bin/quarantine-hermes-tech-legacy-runtime
```

Default mode is `check`. Mutation requires the explicit `apply` argument.

The operator must fail closed unless:

- the two exact legacy files are present with the audited SHA256 values, or are already in the exact quarantine targets with those hashes;
- current Hermes Tech runtime ownership and loopback bind are healthy;
- the rollback container remains exited with the expected identity;
- neither legacy path is referenced by systemd or cron;
- public and loopback Hermes Tech health pass;
- Cloudflare readiness is 4/4.

## Quarantine target

The two scripts were moved, not deleted, to:

```text
/home/andris/.quarantine/hermes-tech-v14-legacy-runtime-20260807/
```

Final names remain `setup3.sh` and `fix-port.sh`. They are mode `0400`, so they are retained as evidence/rollback material but are not executable. `MANIFEST.tsv` records original path, quarantine path and exact SHA256.

This quarantine is intentionally separate from the stopped Docker rollback asset. V15 does **not** remove `hermes-blog-legacy-v14` and does not prune the retained image.

## Verified production quarantine

The explicit `apply` was run only after the merged V15 source was synchronized to exact `main` SHA `d193fc9661a66ab0dd5d2e6b919d5c4ca2a8a6ed` and the read-only `check` gate passed.

Production verification established:

- both original mutation-capable legacy paths are absent;
- quarantine `setup3.sh` SHA256 is `7a1455e938354871b46a91dc00bccb6679ad5c2799f1368e7d5b829190604226`;
- quarantine `fix-port.sh` SHA256 is `115566b8f432863370bd4945f960a8f587f8041df7512bb81174388d42210c98`;
- both quarantined scripts and `MANIFEST.tsv` are mode `0400`;
- `hermes-tech-web.service` remained active and enabled;
- Docker remained bound exactly to `127.0.0.1:8089`;
- loopback origin remained HTTP 200;
- direct LAN `192.168.0.180:8089` remained blocked (`curl` rc 7);
- three consecutive public `https://tech.rozkalns.net/` checks returned HTTP 200;
- Cloudflare connector PID remained unchanged at `423466` and HA readiness remained 4/4;
- `hermes-blog-legacy-v14` remained stopped with container ID `5738272eb00eeffd518a9cb3cb236292a37f44bb360e5a4d703956ce82c50397`.

The quarantine therefore removed the remaining host-local paths that could accidentally recreate the old wildcard runtime without changing the authoritative production runtime.

## Forbidden actions

V15 must not:

- stop, start, restart, disable or reconfigure `hermes-tech-web.service`;
- stop, start, restart or replace `cloudflared.service`;
- run `docker rm`, `docker run`, `docker create`, `docker start`, `docker stop` or `docker restart` as a mutation;
- edit Cloudflare routes or Access;
- edit UFW;
- alter Hermes Tech cron/timers or published content;
- update or pull Nginx;
- delete the quarantined legacy scripts or rollback container.

## Production boundary

Merging V15 performed no production mutation. The later explicit `apply` invocation was the separately confirmed host cleanup change and is now complete.

The retained quarantine evidence, stopped rollback container and exact retained image remain intentionally preserved. Their eventual removal is a separate reviewed cleanup decision.
