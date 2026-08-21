# FAST-LANE v2.1 Hybrid — RPi5_main

This repository adopts the shared FAST/STRICT vocabulary with a fail-closed host policy.

## FAST

FAST is Git-only: documentation, source, tests and reviewed policy code that neither reads protected runtime data nor mutates the host. A FAST batch may include 2-5 closely related same-risk work items and up to two scope-preserving corrective commits.

## STRICT

STRICT is the default for any host/runtime interaction: sudo/root, package install/remove/upgrade, services/timers, Docker, networking/firewall/DNS/Cloudflare Tunnel, SSH/users/mounts/kernel, backups, databases/application data, secrets/credentials, protected configuration or runtime inspection. Uncertain classification is STRICT.

FAST source work may prepare a future strict operation, but execution/installation/activation always needs a separate exact owner authorization.

## CI and evidence

Existing host/security validation remains authoritative. Phase 1 does not weaken or selectively skip host-protective checks. Produce one Ready receipt; immediately before merge refresh mutable GitHub evidence only.

Merge remains explicit owner authority and never authorizes host/runtime mutation.
