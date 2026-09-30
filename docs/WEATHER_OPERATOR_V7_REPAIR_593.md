# Weather v7 broker registration / Git trust repair (#593)

Status: SOURCE-ONLY / LIVE REPAIR NOT AUTHORIZED

This document is the canonical recovery handoff for `RPi5_main#593`. It records the fail-closed repair needed after the first Gate-3 dispatch attempt and does not authorize any host mutation by itself.

## Proven failure

The first fresh Gate-3 authorization was `ops-workflows#65`, request `73a9beec-8ae5-4c9e-aee8-739427543a6e`. It is closed `not_planned` and is permanently non-reusable.

The broker failed before the Weather-v7 operator mutation plan began. The installed host-capability registration was created by the Gate-2 installer with the installer linked-worktree path as `manager_checkout`; the broker contract requires the canonical primary checkout named `RPi5_main`. This deterministically produces the fail-closed registration identity error.

A second trust-boundary defect is fixed in the same source envelope: the systemd broker runs as root against the user-owned manager repository. Its Git execution therefore needs explicit, exact, command-scoped trust. The repaired broker uses only `git -c safe.directory=<canonical RPi5_main manager> -C <canonical RPi5_main manager> ...`. Wildcard trust, persistent global/system Git configuration, ownership changes and caller-selected paths remain forbidden.

## Source changes

`#593` changes the first-install installer so future registrations derive the canonical manager from `git rev-parse --git-common-dir` rather than recording the installer worktree.

For the already-installed capability, the owner-gated repair is intentionally smaller than a reinstall. The repair contract is `ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-repair.json` and the default read-only entrypoint is `scripts/repair-weather-operator-v7-host-capability-registration.py`.

The repair source checkout is fixed as `RPi5_main-weather-v7-host-capability-repair-source-trusted` and must be exact current `main`, detached, clean, at the reviewed origin, with exact-main CI successful.

The repair mutation budget is exactly two filesystem operations:

1. atomic replacement of `/usr/local/libexec/rozkalns-weather-operator-v7-privileged-broker`;
2. atomic replacement of `/etc/rozkalns-weather-operator-v7-capability/registration.json`.

The other 14 installed host-capability artifacts must remain byte-identical to reviewed source. The existing Weather operator must remain at predecessor SHA-256 `4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f`; the v7 operator checkout must remain absent and the v6 checkout must remain present.

There is no systemd/socket/timer mutation in this repair. The socket already starts a fresh broker process for each request, so replacing the executable and registration is sufficient for the next separately authorized dispatch. There is no operator replacement, v7 checkout creation, Docker/Weather application change, SQLite/corpus mutation, network/Cloudflare change, credential/secret change, permission broadening, automatic retry, cleanup or rollback.

## Recovery order

The current incident recovery order supersedes the earlier initial-install sequence for this lane:

1. merge the reviewed `RPi5_main#593` source and require successful exact-main CI;
2. under a separate exact owner LIVE gate, materialize `RPi5_main-weather-v7-host-capability-repair-source-trusted` using at most one reviewed `git fetch origin main` and one fixed detached `git worktree add`;
3. run the repair installer read-only preflight and prove the known predecessor closure;
4. under that bounded owner repair authorization, perform only the two fixed atomic replacements above;
5. collect sanitized read-only closure proving canonical manager registration, repaired broker identity, unchanged socket/service/module closure, predecessor operator, absent v7 checkout and preserved v6 checkout;
6. JIT rebind `ops-workflows#63` to the then-current exact `RPi5_main/main` SHA;
7. create a brand-new owner-authored Weather-v7 LIVE-AUTH UUID — never reopen or reuse `ops-workflows#65`;
8. allow the existing identity-only caller/timer to dispatch Gate 3 without manual service restart;
9. verify the v7 operator exact target SHA and preserved v6 checkout;
10. return to `rozkalns_weather#136` for public Weather rollout reconciliation.

## Fail-closed rule

The repair authorization is consumed at its first authorized mutation. Any error or drift after that point permits only minimum-sufficient read-only evidence and STOP. No retry, rollback, cleanup, alternate target, worktree remove/prune/repair, service restart or expanded root authority is implied.

Source merge does not authorize LIVE. The conversational agent never gains `sudo` or generic root authority.
