# RPi5 visual verification

This is the canonical host-side visual verification path for RPi5-hosted web UIs.

## Default rule

When pixel-level visual inspection of an RPi5-hosted web UI is needed, prefer the installed host wrapper:

```bash
~/.local/bin/ui-proof <URL> [label] [output-dir]
```

The wrapper uses **Playwright with the system Chromium**. Do not use raw `chromium --screenshot` as the normal verification path; on this host it produced D-Bus/GCM lifecycle noise and could hang after rendering.

Running `ui-proof` is host/runtime execution. It requires current applicable LIVE authority under `AGENTS.md`; this document does not grant runtime, retry, cleanup, rollback, or deploy authority.

## Standard viewports

- Desktop: `1440x900`
- Mobile reference device: Samsung Galaxy A55 / `SM-A556B`
- Galaxy A55 browser viewport: `412x892`

The Galaxy A55 user agent is emitted by the wrapper for the mobile capture.

## Required evidence

A successful run should produce an evidence directory containing:

- `desktop-1440x900.png`
- `mobile-galaxy-a55-412x892.png`
- `dom.html`
- `console.log`
- `pageerrors.log`
- `manifest.txt`

`manifest.txt` records the target URL, capture time, desktop/mobile HTTP status, Chromium version, engine, mobile model/viewport, console/page-error counts, and SHA-256 hashes for the core evidence files.

## Inspection bridge

After capture, use RDC only for the host-local evidence step: open the generated PNG files with RDC image reading and visually inspect the rendered pixels. GitHub remains the canonical source for repository state, code, issues, PRs, CI, and durable documentation.

For normal visual verification, the expected flow is:

1. Deploy/runtime target is already available under the applicable authority.
2. Run `~/.local/bin/ui-proof` against the local or otherwise intended URL.
3. Require process exit code `0` and review `manifest.txt`.
4. Review `console.log` and `pageerrors.log` separately; a browser console resource error is not automatically a JavaScript `pageerror`.
5. Open both desktop and Galaxy A55 PNG evidence with RDC and perform visual PASS/FAIL inspection.
6. Preserve the evidence path in the work report when it matters to the deployment or acceptance decision.

## Verified baseline

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
/home/andris/.local/share/ui-proof/weather-20260923-playwright-verify/
```

That run contained one desktop browser-console `404` resource message whose exact resource was not identified. It did not produce a `pageerror` and did not prevent either render. Treat future console/resource errors as target-specific evidence to inspect, not as permission to ignore them.

## Durable operator reminder

When an owner asks to **see**, **visually verify**, **compare the rendered UI**, or asks whether a deployed page **looks correct**, use this Playwright `ui-proof` path by default for RPi5-hosted pages. Do not fall back to the Lenovo/Opera workflow unless the task specifically depends on the user's desktop session, extensions, local authentication, or another client-only condition.
