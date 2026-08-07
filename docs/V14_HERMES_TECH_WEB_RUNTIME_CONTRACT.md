# V14 Hermes Tech static web runtime contract

## Status

**Production migration complete — 2026-08-07.**

This contract moves the legacy standalone `hermes-blog` Docker container into
reviewed host infrastructure ownership and narrows the Hermes Tech origin from a
wildcard Docker publish to loopback-only host access.

The reviewed source was merged before any live cutover. Merging V14 performs no
production mutation. Installation, route cutover, runtime cutover and UFW
cleanup were separately confirmed production actions with independent health
checks and rollback gates.

## Ownership boundary

Hermes Tech application deployment owns content generation and publication files only.
It may update `/home/andris/hermes-tech/site/public` and verify the public site,
but it does not own the static web container lifecycle.

`RPi5_main` owns the `hermes-blog` container lifecycle.

The shared `cloudflared.service` remains separately owned by `RPi5_main` under
the V13 contract. Neither the Hermes Tech application deploy nor this static-web
runtime may start, stop, replace, reconcile, roll back or hold credentials for
the shared Cloudflare Tunnel connector.

## Final authoritative runtime

The final host runtime is:

- systemd unit: `hermes-tech-web.service`;
- unit source: `ops/systemd/hermes-tech-web.service`;
- installed unit: `/etc/systemd/system/hermes-tech-web.service`;
- container name: `hermes-blog`;
- systemd state: active and enabled;
- Docker restart policy: `no`;
- systemd restart policy: `Restart=on-failure`;
- Docker publish: `127.0.0.1:8089:80` only;
- static content bind:
  `/home/andris/hermes-tech/site/public:/usr/share/nginx/html:ro`;
- JSON-file logging: `max-size=10m`, `max-file=3`.

Systemd is the only restart supervisor. Docker and systemd restart supervision
must not be combined.

## Image identity policy

The migration deliberately preserved the exact production Nginx image bytes.
The legacy running image had no repository tag or repository digest available,
so V14 pins the exact retained local image ID:

```text
sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa
```

The reviewed service uses `--pull=never`. This prevents the network/lifecycle
hardening from silently becoming an Nginx upgrade.

A later Nginx refresh is a separate reviewed change. It should use a registry
digest when possible, perform compatibility and public-site verification, and
retain a rollback image.

The exact legacy container is currently retained in stopped state as:

```text
hermes-blog-legacy-v14
```

Its verified legacy container ID is:

```text
5738272eb00eeffd518a9cb3cb236292a37f44bb360e5a4d703956ce82c50397
```

The retained image and stopped rollback container must not be pruned until the
post-migration observation/cleanup decision is made separately.

## Final origin contract

The final Docker publish is exactly:

```text
127.0.0.1:8089:80
```

The final Cloudflare origin for `tech.rozkalns.net` is:

```text
http://127.0.0.1:8089
```

The production result verified:

- loopback origin HTTP 200;
- direct `http://192.168.0.180:8089/` fails;
- public `https://tech.rozkalns.net/` remains HTTP 200;
- Docker inspection shows only `127.0.0.1:8089` for container port 80;
- no wildcard IPv4 or IPv6 listener remains on 8089;
- the obsolete LAN UFW `8089/tcp` allow rule is removed.

The route was changed before the container cutover because the legacy wildcard
listener already accepted loopback traffic. This allowed the Cloudflare route
change to be proven independently before the runtime replacement.

## Verified production migration

The migration completed in separately gated steps on 2026-08-07.

### 1. Source and image preflight

The RPi5 checkout was synchronized to the exact merged V14 source. The reviewed
unit SHA256 was verified before installation, the exact retained image ID was
present locally, and the legacy container was still healthy on both loopback and
public paths.

The shared Cloudflare connector remained on the existing host service with four
active edge connections.

### 2. Install-only gate

The exact reviewed unit was installed as `root:root` mode `0644`, passed
`systemd-analyze verify`, and `daemon-reload` completed.

The unit was deliberately left inactive and disabled during this gate. The
legacy wildcard container continued serving traffic unchanged.

### 3. Cloudflare route cutover

Only the `tech.rozkalns.net` origin was changed from the LAN address to:

```text
http://127.0.0.1:8089
```

While the legacy container still ran, five consecutive public checks returned
HTTP 200. The shared Cloudflare connector PID remained unchanged and readiness
remained four active edge connections.

### 4. Runtime cutover and safe retry

The legacy container was renamed to `hermes-blog-legacy-v14` and preserved as a
rollback asset before the reviewed systemd runtime was started.

The first cutover attempt reached the correct new runtime state — exact image,
Docker restart policy `no`, loopback-only bind — but the operator verification
script had an `ERR`-trap bug: the intentionally failing direct-LAN curl was
mistaken for a transaction failure. Automatic rollback restored the legacy
container, and both loopback and public health returned HTTP 200.

No runtime defect was identified. The verification script was corrected so the
expected non-zero LAN curl result was handled inside an `if` condition rather
than triggering the rollback trap.

The second cutover then passed:

- `hermes-tech-web.service`: active and enabled;
- new `hermes-blog` uses the exact pinned image;
- Docker restart policy: `no`;
- binding: exactly `127.0.0.1:8089`;
- direct LAN connection: blocked (`curl` rc 7);
- five consecutive public checks: HTTP 200;
- Cloudflare connector PID unchanged;
- four active Cloudflare edge connections;
- legacy rollback container preserved and exited.

### 5. UFW cleanup

After the runtime gates passed, the single matching LAN Hermes Tech rule was
identified by specification and removed without assuming a historical rule
number.

Final verification passed:

- no `8089/tcp` LAN allow rule remains;
- Docker still publishes only `127.0.0.1:8089`;
- direct LAN remains blocked;
- five consecutive public Tech checks return HTTP 200;
- Cloudflare connector remains four-of-four ready;
- stopped legacy rollback asset remains preserved.

Final marker:

```text
HERMES_TECH_V14_UFW_FINAL=PASS
```

## Static content and logging contract

V14 preserves the application-data boundary:

```text
/home/andris/hermes-tech/site/public
    -> /usr/share/nginx/html
    read-only
```

The migration did not change Hugo output, collector/digest cron schedules,
pull-deploy behavior, Nginx configuration, application content, container root
filesystem mode, container capabilities, memory limits or CPU limits.

The existing bounded Docker JSON logging policy remains:

```text
max-size=10m
max-file=3
```

## Rollback

The immediate rollback asset remains the stopped legacy container plus the exact
retained image.

If rollback is required while that asset is retained:

1. stop and disable `hermes-tech-web.service`;
2. remove the reviewed `hermes-blog` container if necessary;
3. rename/start `hermes-blog-legacy-v14` as `hermes-blog`;
4. require loopback and public Tech HTTP 200;
5. restore the LAN UFW rule only if direct LAN access is intentionally required;
6. restore the Cloudflare route to a LAN origin only after the legacy listener
   and any required firewall path are healthy;
7. verify the shared Cloudflare connector remains healthy.

The current accepted production architecture does **not** require the LAN UFW
rule or LAN Cloudflare origin. Normal operation is loopback-only.

## Exclusions and later cleanup

V14 did not:

- update Nginx;
- introduce Docker Compose for Hermes Tech;
- change Hugo or content generation;
- change Hermes Tech collector/digest cron schedules;
- change the pull-deploy timer;
- change Cloudflare credentials or Access policy;
- restart or replace `cloudflared.service`;
- change any other application origin or UFW rule.

Legacy host-local setup scripts that could recreate the old wildcard container
should be quarantined or removed only in a separate reviewed cleanup after the
rollback observation window. The stopped legacy container and exact image should
also be removed only after that separate decision.
