# V16 Hermes Tech reboot survival contract

## Status

**Source reviewed in Git; real reboot verification pending.**

V16 proves that the authoritative Hermes Tech web origin survives a real RPi5 reboot under systemd ownership before any V14 rollback asset is retired.

Merging V16 performs no production mutation. It does not reboot the host, start/stop/restart services, change Docker runtime, edit Cloudflare, edit UFW, alter Hermes Tech schedules/content, remove the stopped rollback container, or prune the retained Nginx image.

## Authoritative pre-reboot state

The accepted V14/V15 production state remains:

- systemd unit `hermes-tech-web.service` active and enabled;
- Docker container name `hermes-blog`;
- exact retained image `sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa`;
- Docker restart policy `no`; systemd is the only restart supervisor;
- exact host publish `127.0.0.1:8089:80`;
- read-only content bind `/home/andris/hermes-tech/site/public:/usr/share/nginx/html:ro`;
- JSON-file logging `max-size=10m`, `max-file=3`;
- Cloudflare route `tech.rozkalns.net -> http://127.0.0.1:8089`;
- no direct LAN access to `192.168.0.180:8089` and no UFW 8089 LAN allow rule;
- stopped rollback container `hermes-blog-legacy-v14` with ID `5738272eb00eeffd518a9cb3cb236292a37f44bb360e5a4d703956ce82c50397`;
- V15 legacy launch scripts retained only in non-executable quarantine.

## Reviewed verifier

Authoritative verifier:

```text
ops/bin/verify-hermes-tech-reboot-survival
```

It supports three modes:

- `check` — read-only current-state validation;
- `capture` — validates the current state and atomically records a pre-reboot baseline under `/var/lib/rpi5-main/hermes-tech-reboot-survival.env`;
- `verify` — after a separately authorized real reboot, validates the new boot against the recorded baseline.

The verifier itself never initiates a reboot.

The verifier is intentionally root-operated because it must inspect UFW state and write the protected baseline file. Root execution does not grant it permission to mutate Docker, systemd service state, UFW, or Cloudflare.

## Capture contract

Before the reboot, `capture` must fail closed unless:

- `hermes-tech-web.service` is active and enabled;
- the installed unit matches the reviewed SHA256;
- `hermes-blog` uses the exact retained image, Docker restart policy `no`, exact loopback publish, read-only content bind and expected logging;
- loopback and public Tech health pass;
- direct LAN access fails;
- UFW is active and contains no 8089 rule;
- Cloudflare connector is active with HA readiness 4/4;
- the stopped rollback container has the expected identity;
- the retained image exists locally;
- the two original V15 legacy paths remain absent and both quarantine copies retain their audited SHA256 values and mode `0400`.

The capture records the current kernel boot ID, live container ID, Cloudflare PID, service active-enter monotonic timestamp and capture time. It does not change runtime state.

## Real reboot boundary

A real RPi5 reboot is a separate production maintenance action. V16 source merge and `capture` do not authorize it implicitly.

The reboot must occur only after a successful capture. No rollback asset may be removed before post-reboot verification passes.

## Post-reboot verification contract

`verify` must fail closed unless:

- the current kernel boot ID differs from the captured pre-reboot boot ID;
- `hermes-tech-web.service` is active and enabled;
- its current `ActiveEnterTimestampMonotonic` proves it entered active state during the early boot window (within ten minutes of boot), providing evidence of normal boot enablement rather than a late manual recovery;
- a newly created `hermes-blog` exists and does not reuse the pre-reboot live container ID;
- the recreated container preserves the exact image, restart policy `no`, loopback-only publish, read-only bind and logging contract;
- loopback origin is HTTP 200;
- direct LAN `192.168.0.180:8089` still fails;
- UFW remains active with no 8089 rule;
- public `https://tech.rozkalns.net/` returns HTTP 200 for three consecutive checks;
- `cloudflared.service` is active and HA readiness returns to 4/4;
- the stopped rollback container remains exited with the exact expected ID;
- the retained image still exists;
- V15 quarantine remains intact and the original mutation-capable legacy paths remain absent.

A Cloudflare PID value is evidence only. A process PID is expected to change across a reboot and must not be used as a cross-boot identity guarantee; the kernel boot ID is the authoritative reboot discriminator.

## Forbidden actions

The verifier must not:

- reboot or shut down the host;
- start, stop, restart, enable, disable, mask or reconfigure `hermes-tech-web.service`;
- start, stop, restart or replace `cloudflared.service`;
- run Docker mutation commands such as `run`, `create`, `start`, `stop`, `restart`, `rm` or `rename`;
- edit UFW rules;
- edit Cloudflare routes or Access;
- alter Hermes Tech application content, collector/digest schedules or pull-deploy behavior;
- remove `hermes-blog-legacy-v14`;
- prune or update the retained Nginx image;
- restore or execute the V15 quarantined legacy launch scripts.

## Rollback asset retirement boundary

A successful reboot-survival verification does not itself remove anything. It only establishes that normal boot ownership works.

Retiring `hermes-blog-legacy-v14`, deleting V15 quarantine evidence, or pruning the retained image requires a separate issue, review and explicit production cleanup decision after V16 PASS.