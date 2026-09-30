# RPi5 visual verification

This is the canonical host-side visual verification path for RPi5-hosted web UIs.

## Canonical entrypoint

Pixel-level visual inspection uses Playwright with the system Chromium. Raw `chromium --screenshot` is not a supported normal path because it previously produced lifecycle noise and could hang after rendering.

The renderer remains `ui-proof`, but the canonical operator entrypoint is the guarded launcher:

```bash
~/.local/bin/ui-proof-guarded <URL> [label] [output-dir]
```

The launcher source is `ops/bin/ui-proof-guarded`. It uses fixed current-user install locations for both trusted components:

- lifecycle guard: `~/.local/bin/rpi5-browser-lifecycle`;
- renderer: `~/.local/bin/ui-proof`.

At runtime the launcher resolves those locations from the executing user's home directory. It never resolves either trusted executable through `PATH` and never copies the URL or renderer label into lifecycle ownership metadata. The lifecycle label is always the public-safe fixed value `ui-proof`.

Direct `~/.local/bin/ui-proof` is non-canonical after guarded-launcher activation. Automation must not bypass a missing or unhealthy guarded launcher by falling back to direct `ui-proof` or raw Chromium.

Running any visual-verification browser path is host/runtime execution and requires current applicable LIVE authority under `AGENTS.md`.

## Source/runtime boundary

Issue #775 / PR #776 added the tracked fail-closed browser lifecycle guard. Issue #778 adds the source-owned guarded `ui-proof` entrypoint and routes repository automation to it.

A source merge does **not** install or replace `~/.local/bin/ui-proof-guarded`, `rpi5-browser-lifecycle`, or `ui-proof` on the host. Installing or updating the host launcher remains a separate exact LIVE operation. Until that activation is explicitly authorized and verified, a missing guarded launcher is a STOP condition rather than permission to use the renderer directly.

## Guarded launch sequence

For every canonical render the launcher performs exactly this high-level sequence:

1. Verify the fixed lifecycle guard and renderer paths are real, current-user-owned regular files, are not symlinks, are not group/world writable, and are owner-executable.
2. Run read-only lifecycle `health` and require exit code `0`.
3. Run the renderer only through:

   ```bash
   /usr/bin/python3 -I ~/.local/bin/rpi5-browser-lifecycle \
     run --label ui-proof --timeout-seconds 180 -- \
     ~/.local/bin/ui-proof <URL> [label] [output-dir]
   ```

4. Run lifecycle `health` again after the guarded renderer exits.
5. Preserve a non-zero renderer/guarded-run exit code, including timeout `124`.
6. If the renderer succeeds but post-run health fails, report failure rather than claiming visual verification success.

The launcher never invokes `cleanup-stale`. Stale-session recovery is a separate mutation class and requires a separate current owner authorization.

## Browser lifecycle ownership

The lifecycle guard is ownership-based rather than process-name-based. For each guarded invocation it:

1. enables Linux child-subreaper behavior for the wrapper process;
2. starts the renderer in a fresh session/process group;
3. records only public-safe ownership metadata: opaque run ID, fixed label, wrapper PID/start-time, leader PID/start-time, timeout and exact observed member PID/start-time identities;
4. refreshes exact child/session ownership while the run is alive;
5. on normal exit, timeout, SIGINT or SIGTERM, signals only processes whose current `/proc/<pid>/stat` identity still matches recorded ownership evidence;
6. removes the run-state record only after no owned process remains.

It never uses process-name-only cleanup, caller-selected PIDs or broad Chromium cleanup. PID/start-time mismatch, unsafe state metadata, ambiguous process-group reuse or another ownership conflict fails closed.

The lifecycle guard does not read process environments, command lines, browser profiles, cookies, browser storage or page/session data. Unrelated browser-like processes are counted only through kernel `comm` metadata and are never treated as owned because of their name.

## Read-only lifecycle health

The underlying public-safe health command is:

```bash
/usr/bin/python3 -I ~/.local/bin/rpi5-browser-lifecycle health
```

The JSON report is limited to bounded lifecycle/resource metadata, including:

- active/stale/ambiguous owned-session counts;
- unrelated browser-process count;
- `MemAvailable` in MiB;
- swap-used percentage;
- blocker codes.

Default resource thresholds are at least 512 MiB `MemAvailable` and no more than 85% swap used.

`PASS` means there is no stale/ambiguous owned record and the resource thresholds pass. Unrelated browser processes alone do not establish ownership and are not automatically killed.

`BLOCKED` includes stale owned state, unsafe/malformed state records, duplicate ownership identity, PID/group/session ambiguity, low available memory or excessive swap use. Do not lower thresholds or delete state to bypass a blocker.

## Separately authorized stale recovery

The tracked recovery command remains:

```bash
/usr/bin/python3 -I ~/.local/bin/rpi5-browser-lifecycle \
  cleanup-stale --min-age-seconds 300
```

This command mutates process/state and is **not** part of normal visual verification. It requires current exact LIVE authorization. Recovery may act only on exact recorded ownership with the wrapper gone and the configured minimum age reached; ambiguity stops without signalling the tree.

## Standard viewports

- Desktop: `1440x900`
- Mobile reference: Samsung Galaxy A55 / `SM-A556B`
- Galaxy A55 browser viewport: `412x892`

## Required renderer evidence

A successful render should produce:

- `desktop-1440x900.png`
- `mobile-galaxy-a55-412x892.png`
- `dom.html`
- `console.log`
- `pageerrors.log`
- `manifest.txt`

`manifest.txt` records target/capture metadata, desktop/mobile HTTP status, Chromium version, engine, mobile model/viewport, console/page-error counts and SHA-256 hashes for the core evidence files. Lifecycle state deliberately does not duplicate page/session evidence.

After capture, RDC is used only for the host-local evidence step: open the generated PNG files and visually inspect rendered pixels. GitHub remains canonical for source, issues, PRs, CI and durable documentation.

## Source verification

`tests/test-browser-lifecycle.py` proves the underlying ownership guard. `tests/test-ui-proof-guarded.py` proves the canonical launcher contract, including:

- missing guard fails before renderer execution;
- blocked pre-health prevents renderer start;
- exact guarded invocation uses fixed label and timeout;
- renderer URL/label/output arguments stay after the renderer boundary and never enter lifecycle label/state;
- timeout/non-zero renderer exits remain non-success;
- failed post-health converts apparent renderer success to failure;
- the launcher contains no broad process cleanup or stale-cleanup fallback;
- routing points to `~/.local/bin/ui-proof-guarded`;
- repeated synthetic launcher runs do not create launcher-owned state.

Both test suites are wired into normal repository validation through `tests/test-shell-syntax.sh`.

These tests prove source semantics only. They do not prove host installation or authorize runtime browser execution.

## STOP conditions

Stop rather than improvise when:

- the canonical guarded launcher is missing on the host;
- lifecycle `health` is `BLOCKED`;
- guard/renderer path metadata is not trusted;
- stale recovery reports PID/group/session ambiguity;
- owned cleanup still has remaining processes after bounded lifecycle handling;
- resolving the incident would require a package upgrade, scheduler/service change, secret/profile/session inspection, or generic process killer.

Those are separate scope/risk decisions.

## Durable operator reminder

When the owner asks to **see**, **visually verify**, **compare the rendered UI**, or asks whether a deployed page **looks correct**, use `ui-proof-guarded`. Do not fall back to direct `ui-proof`, raw Chromium, or the Lenovo/Opera workflow unless the task specifically depends on the user's desktop session, extensions, local authentication or another client-only condition.
