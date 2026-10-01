# AdGuard DNS Phase 4 — DHCPv4 authority migration

Issue: `RPi5_main#797`  
Firewall-readiness follow-up: `RPi5_main#799`

## Target topology

Ultra Hub 7 remains the LAN gateway and Wi-Fi router. AdGuard Home on the RPi5 becomes the only DHCPv4 authority. DHCP clients receive the Ultra Hub as default gateway and the RPi5/AdGuard address as DNS. The RPi5 does not become the LAN gateway. IPv6 is unchanged.

AdGuard Home supports a built-in DHCP server. Its DHCPv4 configuration includes gateway, subnet mask, lease range and lease duration, and by default it advertises itself as DNS. The DHCP host must have a stable/static address.

## Source/live separation

This package defines readiness and a future cutover envelope. It performs no runtime mutation. Fresh read-only preflight after merge must derive the exact DHCPv4 parameters from current evidence without emitting raw client identities.

Firewall readiness is a read-only preflight fact, not permission to change firewall state. The preflight must prove that the host firewall path accepts inbound DHCPv4 server traffic on the selected LAN interface (UDP/67). If that proof is absent or false, readiness is blocked. Any firewall mutation remains outside this package and requires its own explicit owner authorization.

## Required preflight facts

The preflight must prove all of the following:

- Ultra Hub DHCPv4 is currently enabled and is the only active DHCPv4 authority;
- AdGuard Home reports DHCP capability available and DHCPv4 disabled;
- RPi5 has a stable LAN identity suitable for DHCP/DNS service;
- the RPi5 firewall path accepts inbound DHCPv4 server traffic on the selected LAN interface (UDP/67), without changing firewall state;
- the candidate subnet and gateway match the current LAN;
- the candidate pool is inside the LAN subnet and excludes the gateway, RPi5, infrastructure/static addresses, and current reserved addresses;
- the staged DHCP payload advertises Ultra Hub as gateway and RPi5/AdGuard as DNS;
- DHCPv6/RA configuration is untouched;
- ordinary AdGuard DNS health is good before cutover.

Public evidence must contain only booleans, counts, fingerprints and semantic classes. No raw lease table, client IP/MAC/hostname, router credentials/session, or raw application config may be emitted.

## Frozen cutover ordering

A future LIVE authorization may allow at most three forward mutations:

1. Stage the exact AdGuard DHCPv4 configuration with `enabled=false` using the reviewed DHCP configuration API. This must succeed before router DHCP is touched.
2. Disable Ultra Hub DHCPv4 and apply that single router change. No other router field may change.
3. Enable AdGuard DHCPv4 using the exact staged parameters.

There must never be an intentional interval with two enabled DHCPv4 servers. Existing leases are allowed to remain valid during the brief no-DHCP interval between steps 2 and 3.

If any mutation returns an error, times out, produces ambiguous state, or loses authorization certainty after mutation begins: collect only bounded read-only evidence and STOP. No automatic retry, rollback, cleanup, router restart, AdGuard restart, client reconnect, or alternate path is allowed.

## Required postconditions

After step 3, bounded verification must prove:

- Ultra Hub DHCPv4 disabled;
- AdGuard DHCPv4 enabled with the authorized parameter fingerprint;
- exactly one DHCPv4 authority is observable on the LAN;
- advertised default gateway is Ultra Hub;
- advertised DNS is only RPi5/AdGuard;
- AdGuard DNS still answers;
- at least one ordinary client obtains or renews a DHCPv4 lease from AdGuard within the bounded verification window, using sanitized evidence only.

If client lease acquisition cannot yet be proven, the cutover is not declared fully verified. No automatic client mutation is permitted.

## Separate recovery gate

Re-enabling Ultra Hub DHCPv4 after a consumed cutover mutation is rollback and always requires a new explicit owner authorization. Merge never authorizes LIVE, and LIVE cutover never authorizes rollback.

## Explicit non-scope

No IPv6 RA/RDNSS change, routing/NAT change, RPi5 gateway role, NetworkManager address change, firewall change, Docker network change, package upgrade, AdGuard filter/access-control change, client configuration change, or DNS/DoT enforcement is authorized by this package.
