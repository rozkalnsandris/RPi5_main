# AdGuard DNS Phase 3 — Ultra Hub 7 LAN capability proof

Issue: `RPi5_main#794`

Phase 1 fixed private PTR resolution. Phase 2 made the RPi5 resolver path AdGuard-only.
Phase 3 is intentionally separate: determine whether the Vodafone Ultra Hub 7 Kabel can
advertise AdGuard to LAN clients and whether it exposes controls that can enforce DNS policy.

## Public documentation baseline

Vodafone's Ultra Hub 7 Kabel manual documents an Expert-mode **Lokales Netzwerk** menu that
can configure network settings, DHCP-server parameters and static IP addresses. It does not
document a custom DHCP DNS field, IPv6 RDNSS/custom DNS field, outbound DNS-53 policy, or
DoT-specific policy. The Internet menu documents general firewall, port-forwarding, device
blocking, DMZ and DynDNS controls, but those do not prove DNS enforcement capability.

Sources:
- https://www.vodafone.de/downloadarea/250731_UH7_UserManual_German_V5_ScreenReader.pdf
- https://www.vodafone.de/hilfe/router/ultrahub-7-kabel.html

Therefore public documentation is only discovery evidence. It must never be promoted to
`SUPPORTED` or `UNSUPPORTED` for the four Phase-3 capabilities.

## Read-only inspection boundary

The future authenticated inspection must use the router's Expert-mode web UI and reduce
observations immediately to four allowlisted enums:

- `dhcpv4_custom_dns`
- `ipv6_custom_dns_or_rdnss`
- `outbound_dns53_enforcement`
- `dot_enforcement`

Each value is `SUPPORTED`, `UNSUPPORTED`, or `UNKNOWN`.

`SUPPORTED` means the relevant authenticated control is explicitly visible without applying it.
`UNSUPPORTED` means the complete relevant Expert-mode scope was inspected and no such control
exists. Any incomplete, inaccessible, contradictory, or ambiguous state is `UNKNOWN`.

The collector accepts only these enums plus three booleans proving that the inspection was
authenticated, Expert mode was active, and the relevant scope was complete. It does not log in,
read credentials, export configuration, capture session material, enumerate clients, or emit raw
network addresses.

## Readiness

The verifier returns `READY_PHASE3_CAPABILITY_DECISION` only when:

1. collection is read-only and did not consume mutation authority;
2. authenticated Expert-mode inspection is proven;
3. the relevant inspection scope is complete;
4. every privacy flag remains false;
5. all four capabilities are decided as `SUPPORTED` or `UNSUPPORTED`.

Any `UNKNOWN` result is a blocker. A capability decision is **not** a mutation authorization.

## Architecture consequence

If the router cannot advertise custom DNS or IPv6 DNS/RDNSS, the design must move to a separate
DHCP/router capability rather than pretending RPi5 UFW can control LAN clients whose traffic does
not traverse the RPi5.

If DNS-53 or DoT enforcement is unsupported, the repository must document that limitation and,
if enforcement is still required, define a separate router/firewall/bridge architecture lane.

No router, DHCP, IPv6, firewall or AdGuard mutation contract is defined by this source package.
Any future write contract comes only after fresh capability proof and a separate owner decision.
