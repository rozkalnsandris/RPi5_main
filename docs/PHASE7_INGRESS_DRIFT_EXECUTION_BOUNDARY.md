# Phase 7 ingress drift execution boundary

Status: **source-defined / runtime disabled until separate owner gates**  
Issue: `RPi5_main#905`  
Audit source: `RPi5_main#903`

This package closes the execution-boundary gap discovered after the Phase 7 audit source merged.

The canonical checkout preparation boundary is `scripts/rpi5_main_exact_source_prepare.py`. Its default mode is read-only. A later owner-authorized apply can perform only fixed `git fetch --no-tags origin main` followed by `git merge --ff-only <exact SHA>`; the fetch is the first mutation, and any later error is STOP with no retry, cleanup or rollback.

The Cloudflare host operator gains a separate Tunnel capability at `/etc/rpi5-secrets/cloudflare/tunnel-writer.json`. It is never reused from the Access lane. The Tunnel credential is account-owned: provisioning is hidden-controlling-TTY only, verifies it with `GET /accounts/{account_id}/tokens/verify`, then verifies the exact remotely-managed `rpi5-tunnel` using GETs before exclusive-create, and never overwrites an existing secret. The existing Access lane retains its user-owned `GET /user/tokens/verify` behavior.

The fixed Phase 7 runtime action is `/usr/local/sbin/rpi5-cloudflare phase7-ingress-drift-audit`. It verifies the exact checkout before reading the Tunnel secret, passes the token to the existing audit on stdin only, and lets the existing GET-only audit discover the single `rpi5-tunnel` by name. It emits only the existing sanitized evidence schema and performs no remediation.

Later gates remain separate: source merge; exact-source/operator preparation; owner-operated Tunnel secret provisioning; fresh owner authorization for the read-only Phase 7 audit.

## Root-run Git index ownership safety

A successful 2026-10-09 owner-authorized Phase 7 GET-only audit confirmed ingress `PASS` across 13 services, but a subsequent local check found the shared checkout's `.git/index` changed to `root:root 0600`. The owner separately authorized restoration to `andris:andris 0600`. This was incidental Git metadata mutation, not a Cloudflare, Docker or service mutation.

The Phase 7 root operator now prefixes **all** checkout Git calls with `git --no-optional-locks`, including its clean-worktree `status` check. The sanitized audit child is launched with `GIT_OPTIONAL_LOCKS=0` so its existing host collector's Git reads also avoid optional index refresh. This preserves exact-main, canonical-origin, tracked-source and clean-worktree checks; it grants no LIVE authority and does not bypass Git protection. See the official `git-status` background-refresh and `git --no-optional-locks` documentation.

This is source-only until a separately owner-authorized installed-operator upgrade. Do not rerun the root Phase 7 operator using an uncorrected release solely to test the fix.
