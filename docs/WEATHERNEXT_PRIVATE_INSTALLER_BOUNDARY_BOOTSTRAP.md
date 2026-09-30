# WeatherNext installer-boundary bootstrap reachability

Issue `RPi5_main#723` defines the source prerequisite needed before `#721` can resume.

## Why this exists

The installed WeatherNext privileged entrypoint imports its dispatcher from the root-owned trusted installer checkout. The known trusted checkout is still at `79372e48ac53bf6d00142578b6543bc33a72a692`, whose dispatcher does not know `rpi5.weathernext-private-installer-boundary.refresh.v1`. A route that exists only on current `main` is therefore not reachable through the stale entrypoint.

The new bootstrap launcher is intentionally a **separate capability**. It does not replace the stale entrypoint and it does not perform the `#700` refresh during bootstrap installation.

## Source contract

`ops/contracts/weathernext-private-installer-boundary-bootstrap-v1.json` freezes:

- source entrypoint: `ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap`;
- future installed path: `/usr/local/sbin/rpi5-weathernext-private-installer-boundary-bootstrap`;
- one separate future mutation category, `filesystem.weathernext-private-installer-boundary-bootstrap-install`, maximum one operation;
- caller authority at execution: authorization issue number only;
- fixed future `#721` runtime path: `ops/bin/rpi5-weathernext-private-installer-boundary-refresh-runtime`;
- bootstrap interface: `rozkalns.weathernext-private-installer-boundary-refresh-bootstrap-callable.v1`;
- no retry, cleanup or rollback;
- no LIVE authority from source merge.

The launcher first verifies the known stale trusted-checkout and installed-entrypoint provenance. It then resolves only the canonical `andris` `RPi5_main` checkout, requires reviewed origin, clean worktree, and `HEAD ==` the reviewed origin's current `main`. It reads only the fixed future runtime path, requires mode `100755`, verifies the read bytes against the exact-main Git blob, and executes the already-read verified bytes through the fixed `run_from_bootstrap(issue_number)` interface.

The launcher never accepts repository, path, command, argv, environment, destination, or source SHA from its caller and has no Git mutation allowlist.

## Handoff back to #721

1. Merge #723 source and require exact-main CI.
2. Re-run a fresh read-only preflight. The known stale boundary and bootstrap target must still match the contract.
3. Obtain a **separate owner LIVE authorization** for exactly one bootstrap-install mutation. Source merge alone grants none.
4. Install only the exact reviewed bootstrap source at the fixed root-owned `0755` target and verify byte identity. Any error after the first mutation is STOP; no retry/cleanup/rollback.
5. Only after that bootstrap activation is verified may `#721` resume source work. Its refresh runtime must be a fixed executable at the contract path and expose the fixed bootstrap interface.
6. `#721` merge still grants no LIVE. The actual `#700/#721` stale-to-exact refresh requires its own fresh exact owner LIVE authorization and retains the original three-category mutation budget.

The bootstrap installation and the later installer-boundary refresh are intentionally distinct authorization and mutation classes.
