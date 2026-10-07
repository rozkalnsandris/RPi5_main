# Phase 7 ingress drift execution boundary

Status: **source-defined / runtime disabled until separate owner gates**  
Issue: `RPi5_main#905`  
Audit source: `RPi5_main#903`

This package closes the execution-boundary gap discovered after the Phase 7 audit source merged.

The canonical checkout preparation boundary is `scripts/rpi5_main_exact_source_prepare.py`. Its default mode is read-only. A later owner-authorized apply can perform only fixed `git fetch --no-tags origin main` followed by `git merge --ff-only <exact SHA>`; the fetch is the first mutation, and any later error is STOP with no retry, cleanup or rollback.

The Cloudflare host operator gains a separate Tunnel capability at `/etc/rpi5-secrets/cloudflare/tunnel-writer.json`. It is never reused from the Access lane. Provisioning is hidden-controlling-TTY only, verifies the active token and exact remotely-managed `rpi5-tunnel` using GETs before exclusive-create, and never overwrites an existing secret.

The fixed Phase 7 runtime action is `/usr/local/sbin/rpi5-cloudflare phase7-ingress-drift-audit`. It verifies the exact checkout before reading the Tunnel secret, passes the token to the existing audit on stdin only, and lets the existing GET-only audit discover the single `rpi5-tunnel` by name. It emits only the existing sanitized evidence schema and performs no remediation.

Later gates remain separate: source merge; exact-source/operator preparation; owner-operated Tunnel secret provisioning; fresh owner authorization for the read-only Phase 7 audit.
