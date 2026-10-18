# Ausmalwiese Stats Gate A D1 runtime v1 (#996)

**SOURCE ONLY. NO MERGE. NO LIVE. NO D1 WRITE. NO CLOUDFLARE WRITE.**

This boundary implements only the additive Stats Gate A migration reconciled in
PR #1100. It does not replace or weaken the later Worker takeover gate.

## Frozen inputs

- reviewed `coloring-pages` evidence commit:
  `7f07c226105e26c0ca9cf91eb150a3e8f585c5ea`
- exact local runtime checkout commit:
  `34287444c32b3d04a89141748b0e645be6b4e5f2`
- Worker blob:
  `c2ac9da6e0701103e0041b30db7dfbea4298f96c`
- Wrangler config blob:
  `3733263a391274f2b6b0f2023c8656565bde8e1a`
- additive migration blob:
  `b5346c05cb27de1010dab2027b0b923e999af775`
- Gate A remote evidence SHA-256:
  `3397daf651bbe60512167817bcef9f02421c71f877bef0a92afc44821fb08af6`
- pre-schema SHA-256:
  `470f40bab9b7e2bfcf68b73cfa3aad7bf171bcb764fdfc391c09d1b4fa85e9f6`

The pre-schema digest means all three migration targets are absent:
`like_cookie_sessions`, `archived_like_totals`, and
`idx_like_cookie_sessions_expiry`.

## Runtime

Source:
`scripts/ausmalwiese_stats_gate_a_d1_runtime_v1.py`

Git blob:
`addccfa3fc54da494102d0b472f785575e9d4f55`

Future installed entrypoint:
`/usr/local/sbin/rpi5-ausmalwiese-stats-gate-a-d1-migrate`

The installed file must be root-owned mode `0500`. Wrangler is the already
installed `<fixed-operator-home>/.local/bin/wrangler` and executes only as fixed user
`andris`; the runtime itself does not open credential files or print credential
content.

No package install is used. Wrangler version `4.135.0` is checked from the
local package metadata rather than by invoking `wrangler --version`.

Every Wrangler subprocess gets:

`WRANGLER_WRITE_LOGS=false`

The runtime compares `.wrangler/logs` file metadata before/after preflight,
mutation, and post-verification. A pre-mutation log delta blocks execution. Any
post-mutation log delta is terminal unknown state: no retry, rollback, cleanup,
or alternate path.

## Preflight

The installed runtime must, in this order:

1. verify its root-owned installed entrypoint;
2. verify the exact local `coloring-pages` checkout commit
   `34287444c32b3d04a89141748b0e645be6b4e5f2`;
3. verify Worker/config/migration working bytes against their exact Git blobs;
   those three blobs are unchanged from the reviewed evidence commit;
4. verify local Wrangler package version;
5. read versions list, deployments list, and active version detail;
6. run only the three fixed read-only D1 schema queries;
7. require remote evidence SHA-256
   `3397daf651bbe60512167817bcef9f02421c71f877bef0a92afc44821fb08af6`;
8. require pre-schema SHA-256
   `470f40bab9b7e2bfcf68b73cfa3aad7bf171bcb764fdfc391c09d1b4fa85e9f6`;
9. require all three target schema objects to remain absent;
10. re-check exact application bytes immediately before mutation dispatch.

The Gate A contract deliberately permits latest-uploaded to differ from the one
100% active version. That exception is not inherited by Worker upload/deploy.

## Single mutation

The only D1 mutation capability is equivalent to:

```text
<fixed-operator-home>/.local/bin/wrangler d1 execute DB --remote --file cloudflare/stats-cookie-like-migration.sql --yes --config cloudflare/wrangler.stats-worker.jsonc
```

There is no arbitrary SQL mutation path, alternate database/file, cleanup
migration, Worker upload/deploy, secret provisioning, retry, rollback, or
cleanup command.

After dispatch, a non-zero result is terminal unknown state. A zero result is
not sufficient: the runtime repeats only the three fixed schema reads and must
prove the exact semantic post-schema.

## Owner binding

A future LIVE command must bind all three values:

- remote evidence SHA-256;
- pre-schema SHA-256;
- migration Git blob.

The installed entrypoint also requires fixed confirmation
`OWNER-AUTHORIZED-STATS-GATE-A-D1-MIGRATION`.

Source merge does not authorize runtime installation. Runtime installation does
not authorize D1 mutation.

## Installer

Source:
`scripts/install-ausmalwiese-stats-gate-a-d1-runtime-v1.py`

The installer may install only the exact runtime blob
`addccfa3fc54da494102d0b472f785575e9d4f55` into the fixed target. A first
install still requires target absence and bounded GNU `cp` no-clobber
semantics.

For an already installed Gate A runtime, the only upgrade predecessor is
RPi5_main `6761b8b15557204d1a16d810df6a348f0d58dfb1` with runtime blob
`eb6dfa99deb1467c102ea12b572128fef3041ccf`. Upgrade preflight reconstructs
those historical bytes, requires the installed target to be a non-symlink
`root:root 0500` single-link file with the exact SHA-256, and checks sudo
capability for one fixed `/usr/bin/install` replacement. The upgrade has no
alternate predecessor or arbitrary target.

Both install paths require a clean exact `RPi5_main/main` checkout, trusted
origin, sealed memfd input and post-write root metadata/SHA-256 verification.
The installer contains no Wrangler/Cloudflare transport, credential read, D1
action, package installation, retry, rollback, or cleanup surface.
