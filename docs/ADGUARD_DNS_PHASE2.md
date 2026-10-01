# AdGuard DNS hardening — Phase 2 host resolver self-consistency

This document extends the source-owned remediation path for `RPi5_main#788`
after Phase 1 private-PTR correctness was applied and verified. Phase 2 is a
separate NetworkManager trust boundary. Source readiness does not authorize a
host/runtime mutation.

## Read-only finding

A separate owner-authorized read-only audit proved that the RPi5 host still had
fallback resolver paths around loopback AdGuard:

- the active NetworkManager profile used `ipv4.method=manual`;
- its explicit IPv4 DNS set reduced to `loopback` plus `ipv4_public`;
- `ipv4.ignore-auto-dns=yes` was already set;
- IPv6 used `ipv6.method=auto`, had no explicit IPv6 DNS, and had
  `ipv6.ignore-auto-dns=no`;
- NetworkManager runtime DNS and NetworkManager-generated `/etc/resolv.conf`
  reduced to `loopback`, `ipv4_public`, and `ipv6_link_local`;
- `options rotate` was absent, so loopback AdGuard remained first while the
  other entries were fallback paths;
- `systemd-resolved` was inactive and ordinary system DNS was healthy.

No raw resolver address, device name, connection UUID, credential, or protected
configuration value belongs in public evidence.

## Phase-2 preflight

`ops/bin/adguard-resolver-phase2-preflight` reproduces the bounded evidence. It
reads only the exact NetworkManager fields needed for this gate, reduces DNS
addresses to classes, and emits short one-way fingerprints for the active
profile and default-route device instead of their identities.

`ops/bin/adguard-resolver-phase2-preflight-verify` reaches `READY_PHASE2` only
for the exact observed topology:

1. the collector is PASS with no mutation or authorization use;
2. the privacy boundary is intact;
3. the active profile has exactly one loopback and one public IPv4 DNS entry;
4. explicit IPv4 automatic DNS remains ignored;
5. IPv6 is automatic, has no explicit DNS, and still accepts automatic DNS;
6. runtime DNS and NetworkManager-generated `resolv.conf` contain exactly the
   three classes `loopback`, `ipv4_public`, and `ipv6_link_local`;
7. resolver rotation is absent and `systemd-resolved` is inactive;
8. ordinary system DNS and direct loopback AdGuard DNS answer;
9. TCP and UDP port 53 listeners are present.

Any shape drift blocks the operation instead of widening it.

## Frozen Phase-2 mutation contract

`ops/contracts/adguard-host-resolver-phase2-v1.json` is source-disabled and
non-authorizing. A later explicit LIVE authorization is required after merge,
exact-main verification, and a fresh `READY_PHASE2` preflight.

The future operation is limited to at most two forward NetworkManager writes:

1. persistently modify the freshly identified active default-route profile with
   only `ipv4.dns=127.0.0.1` and `ipv6.ignore-auto-dns=yes`;
2. only after step 1 succeeds, run `nmcli device reapply` for the freshly
   identified default-route device so the saved profile is applied without
   disconnecting the link.

The operation must not change IPv4 or IPv6 addresses, routes, gateways, or
methods. It must not write `/etc/resolv.conf` directly, disconnect/reconnect
the device, cycle the connection, restart NetworkManager, mutate AdGuard,
Docker, firewall, or router state, or take an alternate mutation path.

Authorization must bind the exact merged source SHA, operation ID, fresh
preflight evidence identity, active-profile fingerprint, default-route-device
fingerprint, and the two-write limit. Authorization is consumed by the first
profile write.

## Why these two properties

NetworkManager documents `ignore-auto-dns=yes` as ignoring automatically
learned DNS and search data when the IP method is `auto`, leaving only explicit
profile DNS. Therefore Phase 2 disables automatic IPv6 DNS while preserving
IPv6 addressing and routes.

The explicit public IPv4 resolver is in the same active profile as loopback.
NetworkManager documents `dns-priority` as ordering DNS between active
connections and explicitly notes that it does not disambiguate multiple DNS
servers within one profile. Removing the explicit public IPv4 entry is
therefore the narrow fix; changing DNS priority is not a substitute.

NetworkManager's `Reapply` operation updates an active device from profile
changes without deactivating it, avoiding a connection down/up cycle.

Upstream references:

- NetworkManager 1.42 settings reference:
  `https://networkmanager.dev/docs/api/1.42/nm-settings-nmcli.html`;
- NetworkManager device `Reapply` API:
  `https://www.networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.Device.html`.

## Postconditions and failure semantics

After mutation, bounded verification must prove all of the following:

- saved-profile IPv4 DNS is exactly one loopback entry;
- saved-profile `ipv6.ignore-auto-dns` is true;
- runtime DNS contains only the `loopback` class;
- NetworkManager-generated `/etc/resolv.conf` contains exactly one loopback
  nameserver;
- ordinary system DNS and direct loopback AdGuard DNS answer;
- TCP and UDP port 53 listeners remain present.

Any error, timeout, ambiguity, identity drift, unexpected profile state, or
failed postcondition after the first write means sanitized evidence plus STOP.
There is no automatic retry, rollback, reconnect, restart, cleanup, or
alternate mutation path.

## Later gates remain separate

Phase 2 does not authorize or solve router-side IPv6 RDNSS/DHCP capability,
LAN-wide DNS/DoT enforcement, AdGuard access controls/rate limits, Docker
hardening, or filter/telemetry cleanup. Those remain independent gates.
