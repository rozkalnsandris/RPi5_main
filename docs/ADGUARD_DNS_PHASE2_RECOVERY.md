# AdGuard DNS hardening — Phase 2 recovery

This document records the fail-closed recovery lane for `RPi5_main#788` after
the first Phase-2 host-resolver LIVE operation completed both frozen writes but
failed its runtime DNS postcondition.

Source readiness remains separate from host/runtime readiness. Nothing in this
document or the accompanying source package authorizes a connection
reactivation.

## Observed post-failure state

Owner-authorized bounded verification after the original Phase-2 operation
proved:

- the saved active profile now has only loopback IPv4 DNS;
- `ipv4.ignore-auto-dns=yes` remains set;
- IPv6 remains `method=auto` with no explicit IPv6 DNS;
- the saved profile has `ipv6.ignore-auto-dns=yes`;
- the explicit public IPv4 resolver is gone from runtime;
- NetworkManager runtime DNS and NetworkManager-generated `resolv.conf` still
  contain loopback plus one IPv6 link-local resolver;
- ordinary system DNS, direct loopback AdGuard DNS, and TCP/UDP port 53 remain
  healthy.

No retry, rollback, reconnect, restart, or cleanup followed the failed
postcondition.

## Recovery diagnosis

A later owner-authorized read-only recovery audit narrowed the remaining DNS
source:

- only one non-loopback NetworkManager connection is active;
- active profile and default-route device fingerprints did not drift;
- the same default-route device exposes a DHCPv6 option named
  `dhcp6_name_servers`;
- DHCPv6 option values were not emitted or retained as evidence;
- the saved profile is already hardened but the active runtime still contains
  the DHCPv6-provided link-local resolver.

The host runs NetworkManager 1.42.4. Its configured Debian Bookworm/Raspberry
Pi repositories currently offer no newer `network-manager` candidate.

NetworkManager 1.58 explicitly documents a fix where `reapply` now honors
`ipv6.ignore-auto-dns` even when DHCPv6 is not restarted. This matches the
observed 1.42.4 limitation: the first Phase-2 `device reapply` preserved the
already-acquired DHCPv6 DNS runtime state.

Upstream references:

- NetworkManager 1.58 release notes:
  `https://networkmanager.dev/blog/networkmanager-1-58/`;
- nmcli device `reapply` and connection activation reference:
  `https://www.networkmanager.dev/docs/api/latest/nmcli.html`;
- NetworkManager single-connect activation semantics:
  `https://networkmanager.dev/docs/libnm/latest/libnm-nm-dbus-interface.html`.

A package upgrade is intentionally not part of this recovery lane. Reaching
NetworkManager 1.58 from the current Bookworm package set would require a
separate package/OS migration decision and a much wider dependency surface.

## Recovery preflight

`ops/bin/adguard-resolver-phase2-recovery-preflight` is a separate sanitized
collector for the post-failure state. It emits only resolver classes, counts,
booleans, and one-way fingerprints. It never emits DHCPv6 option values, raw
resolver addresses, device names, connection UUIDs, credentials, or protected
configuration.

`ops/bin/adguard-resolver-phase2-recovery-preflight-verify` returns
`READY_PHASE2_RECOVERY` only when all of these remain true:

1. NetworkManager is exactly 1.42.4;
2. the saved profile is already hardened to loopback-only IPv4 DNS and
   `ipv6.ignore-auto-dns=yes`;
3. the profile has effective single-connect semantics;
4. exactly one non-loopback NetworkManager device is connected;
5. runtime DNS and `resolv.conf` contain exactly loopback plus IPv6 link-local;
6. DHCPv6 metadata confirms a `dhcp6_name_servers` option on that same device;
7. `systemd-resolved` remains inactive;
8. ordinary DNS, loopback AdGuard DNS, and TCP/UDP port 53 remain healthy.

Any version, topology, identity, resolver-shape, or health drift blocks recovery
instead of widening it.

## Frozen recovery mutation

`ops/contracts/adguard-host-resolver-phase2-recovery-v1.json` is source-only and
non-authorizing.

After merge, exact-main verification, and a fresh `READY_PHASE2_RECOVERY`
preflight, a separate owner LIVE authorization may allow exactly one forward
NetworkManager mutation:

```text
nmcli --wait 90 connection up uuid <fresh-active-profile-uuid> ifname <fresh-default-route-device>
```

The preflight requires effective single-connect semantics. NetworkManager
documents that activating an already-active single-connect profile first
deactivates its current activation. The one-shot activation therefore forces
a full connection reactivation and DHCPv6 runtime rebuild from the already
hardened saved profile instead of attempting another `device reapply`.

A transient network/control-plane interruption is expected. Dispatch of the
single activation command consumes the authorization. If the control channel
drops after dispatch, the command must not be sent again; after transport
returns, only read-only evidence may be collected.

The recovery operation does **not** authorize:

- a separate `connection down` command;
- device disconnect;
- another `device reapply`;
- NetworkManager restart;
- NetworkManager/package/OS upgrade;
- any profile-property write;
- direct `/etc/resolv.conf` write;
- systemd-resolved, AdGuard, Docker, firewall, router, or Cloudflare mutation;
- retry, rollback, reconnect, cleanup, or an alternate mutation path.

## Recovery postconditions

Bounded post-verification must prove:

- the saved profile remains loopback-only for IPv4 DNS;
- saved `ipv6.ignore-auto-dns` remains true;
- runtime DNS contains only the `loopback` class;
- NetworkManager-generated `resolv.conf` contains exactly one loopback
  nameserver;
- ordinary system DNS answers;
- direct loopback AdGuard DNS answers;
- TCP and UDP port 53 listeners remain.

Any error, ambiguity, unexpected transport outcome, identity drift, or failed
postcondition after command dispatch means sanitized evidence plus STOP.
