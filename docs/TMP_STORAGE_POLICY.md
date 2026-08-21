# RPi5 `/tmp` storage and headroom policy

Issue: #201

## Current accepted host policy

The production RPi5 is Debian 12 (bookworm) with systemd 252. The accepted #201
production transaction keeps `/tmp` owned by the `/etc/fstab`-generated
`tmp.mount` and uses a bounded tmpfs policy with these semantics:

- maximum size: `50%` of physical RAM;
- directory mode: `1777`;
- `nosuid` and `nodev` enabled;
- full-atime/strict-atime semantics preserved;
- executable `/tmp` semantics preserved because general-purpose temporary files
  may legitimately need execution;
- no unmount or reboot is required to resize the live tmpfs.

The accepted v4 transaction reported a live size of 2,123,235,328 bytes and
1,916,403,712 bytes available immediately after the change. The size is a
ceiling, not preallocated RAM.

The previous Debian 13/Trixie recommendation to remove the local `/tmp` fstab
entry is not applicable to this host and is superseded by the Debian 12 result.

## Capacity monitoring contract

`ops/bin/rpi5-tmp-headroom` is the source-only checker for the production policy.
A healthy result requires all of the following:

- `/tmp` is `tmpfs`;
- live size is at least 1 GiB, which catches regression to the historical 256 MiB
  ceiling without hard-coding the machine's exact RAM size;
- at least 256 MiB remains available;
- usage is below 85%;
- mode is `1777`;
- the mount is read-write with `nosuid` and `nodev`;
- `noexec`, `noatime`, and `relatime` are absent.

The two capacity thresholds are intentionally conjunctive. The percentage gate
warns before near-exhaustion on the current ~2 GiB tmpfs, while the absolute
256 MiB headroom gate preserves at least the capacity of the old entire tmpfs
for Docker/runc and other host control-plane temporary work.

`rpi5-tmp-headroom.timer` is designed to run the lightweight check five minutes
after boot and every 15 minutes thereafter. A failed check makes
`rpi5-tmp-headroom.service` fail, which is wired to the existing
`rpi5-maintenance-notify@.service` notification path.

`PrivateTmp` must remain disabled for this checker. Enabling it would give the
service a private temporary namespace and could cause it to inspect a different
`/tmp` from the host mount it is intended to protect.

The service must use `ProtectSystem=full`, not `ProtectSystem=strict`. On
Bookworm/systemd 252, `strict` remounts the entire filesystem hierarchy
read-only inside the service mount namespace, which changes the checker's view
of `/tmp` from the host's `rw` mount to `ro` and causes a false `TMP_NOT_RW`
failure. `full` keeps `/usr`, `/boot`, `/efi`, and `/etc` read-only while
preserving the host `/tmp` access mode. Do not compensate with
`ReadWritePaths=/tmp`: the monitor should observe the host mount semantics
rather than manufacture a unit-specific writable exception.

## Large-cache policy

The larger tmpfs ceiling is not permission for build caches to consume `/tmp`
unboundedly. Large or reusable caches should use NVMe-backed per-user or
application cache/workspace locations.

For Node.js module compile cache, the producer should set `NODE_COMPILE_CACHE`
to an NVMe-backed cache directory rather than relying on the default
`os.tmpdir()/node-compile-cache` fallback. npm's normal POSIX cache should also
remain disk-backed (normally under the user's home cache), and workflows that
create phase-specific npm caches in `/tmp` should be redirected once their exact
producer is proven.

No `NODE_COMPILE_CACHE`, `node-compile-cache`, `TMPDIR`, or phase-specific npm
cache producer is currently tracked in `RPi5_main`. Producer provenance must be
established from safe evidence before changing another repository, user setup,
or live service configuration.

## Deployment boundary

This document and the checker/unit sources do not authorize production changes.
Installing or replacing the checker, installing/enabling/starting the timer, or
running `systemctl daemon-reload` on RPi5 are separate host mutations and require
an exact owner authorization with rollback.

The #201 capacity fix itself is already accepted. Remaining acceptance work is:

1. activate the reviewed monitoring source under a separately authorized host
   transaction;
2. prove and redirect the recurring Node/npm cache producer(s);
3. run representative build/admin workloads and confirm `/tmp` remains below the
   alert thresholds.
