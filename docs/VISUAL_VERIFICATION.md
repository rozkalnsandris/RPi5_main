# RPi5 visual verification

This is the canonical host-side visual verification path for RPi5-hosted web UIs.

## Default rule

When pixel-level visual inspection of an RPi5-hosted web UI is needed, use Playwright with the system Chromium. Do not use raw `chromium --screenshot` as the normal verification path; on this host it produced D-Bus/GCM lifecycle noise and could hang after rendering.

The renderer remains `ui-proof`, but issue #775 adds a tracked fail-closed lifecycle guard around browser-backed commands:

- source CLI: `ops/bin/rpi5-browser-lifecycle`;
- source library: `ops/lib/browser_lifecycle.py`;
- default state root after installation: `~/.local/state/rpi5-browser-lifecycle`;
- default resource preflight: at least 512 MiB `MemAvailable` and no more than 85% swap used.

**Source/runtime boundary:** merging the guard source does not install it and does not silently replace the currently installed `~/.local/bin/ui-proof`. Host installation/activation is a separate LIVE operation. Until that later activation is explicitly authorized and verified, do not claim that production `ui-proof` is protected by the new guard.

After an authorized activation, the intended canonical invocation shape is:

```bash
/usr/bin/python3 -I ~/.local/bin/rpi5-browser-lifecycle \
  run --label ui-proof --timeout-seconds 180 -- \
  ~/.local/bin/ui-proof <URL> [label] [output-dir]
```

Never put a URL, cookie, token, account identifier or other private value in `--label`; use a fixed public-safe label such as `ui-proof`.

Running either `ui-proof` or the lifecycle guard is host/runtime execution and requires current applicable LIVE authority under `AGENTS.md`. This document grants no runtime, cleanup, retry, rollback or deploy authority.

## Browser lifecycle ownership

The lifecycle guard is deliberately ownership-based rather than name-based.

For each guarded invocation it:

1. enables Linux child-subreaper behavior for the wrapper process;
2. starts the renderer in a fresh session/process group;
3. records only public-safe ownership metadata: opaque run ID, fixed label, wrapper PID/start-time, leader PID/start-time, timeout and exact observed member PID/start-time identities;
4. periodically refreshes exact child/session ownership while the run is alive;
5. on normal exit, timeout, SIGINT or SIGTERM, sends signals only to processes whose current `/proc/<pid>/stat` identity still matches the recorded ownership evidence;
6. removes the run-state record only after no owned process remains.

It never uses `pkill chromium`, `killall`, process-name-only cleanup or caller-selected PID lists. A PID/start-time mismatch, unsafe state-file metadata, ambiguous process-group reuse or another ownership conflict fails closed instead of killing a process.

The guard does **not** read process environments, command lines, browser profiles, cookies, browser storage or page/session data. Browser-like unrelated processes are counted using kernel `comm` metadata only and are never treated as owned merely because their name looks like Chromium.

## Read-only health/preflight

After installation, the public-safe read-only preflight is:

```bash
/usr/bin/python3 -I ~/.local/bin/rpi5-browser-lifecycle health
```

The JSON report contains only bounded metadata such as:

- active owned session count;
- stale owned session count;
- ambiguous owned-state count;
- unrelated browser-process count;
- `MemAvailable` in MiB;
- swap-used percentage;
- blocker codes.

`PASS` means there is no stale/ambiguous owned record and the configured memory/swap thresholds are satisfied. Unrelated browser processes are reported but are not automatically killed and do not by themselves establish ownership.

`BLOCKED` is expected for any of these conditions:

- stale owned session;
- malformed or metadata-unsafe state record;
- duplicate ownership identity;
- PID/process-group/session reuse ambiguity;
- an unproven process in a numerically matching old group/session;
- available memory below the configured floor;
- swap usage above the configured ceiling.

Do not bypass a blocker by lowering thresholds or deleting state unless the current owner authorization explicitly covers the intended recovery.

## Stale-session recovery

The tracked recovery command is:

```bash
/usr/bin/python3 -I ~/.local/bin/rpi5-browser-lifecycle \
  cleanup-stale --min-age-seconds 300
```

This is **not** a standing cleanup permission. It mutates host process/state and therefore requires a current exact LIVE authorization before use.

Recovery is idempotent and may act only when:

- the recorded wrapper PID/start-time is no longer alive;
- the record is at least the requested age;
- current process identities still match exact recorded ownership, or continuity of the original owned session/process group is mechanically proven;
- no PID reuse, duplicate ownership or unproven group member makes ownership ambiguous.

If ownership is ambiguous, the command stops without signalling that process tree. It never falls back to broad process-name matching.

## Standard viewports

- Desktop: `1440x900`
- Mobile reference device: Samsung Galaxy A55 / `SM-A556B`
- Galaxy A55 browser viewport: `412x892`

The Galaxy A55 user agent is emitted by the renderer for the mobile capture.

## Required evidence

A successful `ui-proof` render should produce an evidence directory containing:

- `desktop-1440x900.png`
- `mobile-galaxy-a55-412x892.png`
- `dom.html`
- `console.log`
- `pageerrors.log`
- `manifest.txt`

`manifest.txt` records the target URL, capture time, desktop/mobile HTTP status, Chromium version, engine, mobile model/viewport, console/page-error counts, and SHA-256 hashes for the core evidence files.

The browser lifecycle state deliberately does **not** duplicate those page/evidence details. Its state is limited to process ownership metadata required for safe cleanup.

## Inspection bridge

After capture, use RDC only for the host-local evidence step: open the generated PNG files with RDC image reading and visually inspect the rendered pixels. GitHub remains the canonical source for repository state, code, issues, PRs, CI, and durable documentation.

After the lifecycle guard is separately activated, the expected flow is:

1. Run `rpi5-browser-lifecycle health` and require `PASS`.
2. Run `ui-proof` through `rpi5-browser-lifecycle run`, not directly.
3. Require guarded process exit code `0` and review `manifest.txt`.
4. Review `console.log` and `pageerrors.log` separately; a browser console resource error is not automatically a JavaScript `pageerror`.
5. Open both desktop and Galaxy A55 PNG evidence with RDC and perform visual PASS/FAIL inspection.
6. Run lifecycle `health` again and require no stale/ambiguous owned session.
7. Preserve the evidence path in the work report when it matters to the deployment or acceptance decision.

A timeout returns exit code `124` only after the guard has attempted exact-owned cleanup. Signal-driven interruption returns the conventional `128 + signal` code after the same cleanup path. Ownership ambiguity is a fail-closed blocker rather than permission to kill more broadly.

## Source verification

`tests/test-browser-lifecycle.py` is wired into `make test` through `tests/test-shell-syntax.sh`. It deterministically covers:

- a successful parent that leaves a descendant behind;
- timeout cleanup;
- crash/SIGKILL followed by exact stale recovery;
- idempotent repeated stale cleanup;
- preservation and reporting of an unrelated process named `chromium`;
- PID reuse ambiguity;
- repeated guarded runs without state/process accumulation;
- absence of broad `pkill`/`killall` cleanup in the tracked implementation.

These tests prove source semantics only. They do not prove that the production host has installed or adopted the guard.

## Verified renderer baseline

Verified on 2026-09-23 against the weather UI at `http://127.0.0.1:9180`:

- engine: `playwright-system-chromium`
- system Chromium: `153.0.8010.47`
- desktop HTTP status: `200`
- Galaxy A55 HTTP status: `200`
- Playwright process exit: `0`
- page errors: `0`
- desktop and Galaxy A55 screenshots: successfully generated and visually readable through RDC

The verification evidence was created under:

```text
~/.local/share/ui-proof/weather-20260923-playwright-verify/
```

That run contained one desktop browser-console `404` resource message whose exact resource was not identified. It did not produce a `pageerror` and did not prevent either render. Treat future console/resource errors as target-specific evidence to inspect, not as permission to ignore them.

## STOP conditions

Stop rather than improvise when:

- lifecycle `health` is `BLOCKED` and the blocker cannot be resolved without a new mutation class;
- stale cleanup reports PID/group/session ambiguity;
- a state path is a symlink, has the wrong owner or has group/world access;
- the guarded renderer cannot enter a dedicated session/process group;
- owned cleanup still has remaining processes after bounded TERM/KILL handling;
- resolving the incident would require a Hermes/`agent-browser` package upgrade, scheduler change, service restart, secret/profile/session inspection or a generic process killer.

Those are separate scope/risk decisions and are not authorized by the #775 source outcome.

## Durable operator reminder

When an owner asks to **see**, **visually verify**, **compare the rendered UI**, or asks whether a deployed page **looks correct**, use the Playwright `ui-proof` path. Once the lifecycle guard has been separately activated, run it through the guard by default. Do not fall back to the Lenovo/Opera workflow unless the task specifically depends on the user's desktop session, extensions, local authentication, or another client-only condition.
