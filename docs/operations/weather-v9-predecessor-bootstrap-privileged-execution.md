# Weather v9 predecessor bootstrap privileged execution

Issue: #628

The predecessor bootstrap source from #625/#626 is correct, but the canonical preflight must inspect root-owned `0700` Weather v9 runtime directories. Linux path resolution requires search permission on every directory component, so running that preflight as the ordinary `andris` identity fails closed before any durable-state mutation. This recovery keeps those permissions unchanged.

## Boundary

The capability is a dedicated bootstrap-only systemd socket service. It does not widen the normal Weather v9 broker and does not add generic `sudo` or a caller-selected root command surface.

The caller may request only:

- `preflight` — fixed read-only predecessor bootstrap validation; no LIVE authorization required;
- `apply` — the same fixed predecessor bootstrap mutation, with only `authorization_issue_number` supplied by the caller.

No caller-controlled executable, path, argv, environment, uid/gid, SHA/hash, target, or arbitrary operation is accepted.

## Root execution

systemd starts one fixed `oneshot` root broker through a `0600` Unix socket owned by `andris`. The service keeps `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`, namespace/kernel/control-group protections, a minimal capability bounding set, and fixed `ReadWritePaths` limited to the Weather v9 config/state roots and this capability's replay root.

The capability has its own root-owned registration. It records the reviewed source checkout, canonical manager identity, exact source SHA, and release/unit hashes, so bootstrap execution does not depend on the missing Weather v9 `registration.json`.

Any Git subprocess runs as the canonical manager uid/gid with no supplementary groups, `shell=False`, a fixed environment, fixed working directories, and an explicit read-only Git argv allowlist.

## LIVE authorization

`preflight` is read-only and does not consume LIVE authority.

`apply` requires a fresh owner-authored public GitHub LIVE authorization issue. The root broker reconstructs the fixed authorization server-side: exact source SHA, predecessor SHA, operation, target alias, host, creation-time TTL, unchanged double fetch, direct owner identity (not GitHub App mediated), and no-retry/no-cleanup/no-rollback flags. The caller cannot submit those values.

The authorization is durably consumed in the capability replay root before the existing Weather v9 predecessor bootstrap begins its first DB/registration mutation. Any later failure is fail-closed and non-reusable.

## Source delivery versus LIVE

The source installer only defines the exact files, modes, registration, and systemd unit identities. Source merge does not install, enable, reload, start, or invoke the capability.

Required LIVE sequence after merge:

1. materialize the exact merged RPi5_main source on `rpi5`;
2. separately authorize installation of this root-owned capability;
3. separately authorize systemd daemon-reload/socket activation;
4. run root broker `preflight`;
5. create/fetch a fresh exact owner LIVE authorization for `apply`;
6. run one `apply`;
7. verify predecessor-bound registration and replay DB;
8. run the already-reviewed post-#83 broker-refresh preflight and continue through its separate LIVE gate.

No automatic retry, cleanup, rollback, permission relaxation, generic root shell, or alternate mutation path is part of this recovery.
