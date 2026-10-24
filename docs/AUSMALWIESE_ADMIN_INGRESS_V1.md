# Ausmalwiese ADMIN ingress v1

Issue: RPi5_main #1151  
Canonical origin service: Ausmalwiese ADMIN ZIP publisher from #1149  
Owner-approved hostname: `admin.ausmalwiese.de`

## Source policy

- trust class: `ADMIN`
- delivery: shared RPi5 Cloudflare Tunnel
- desired origin: loopback-only publisher on port 8765
- Access scope: exact owner
- Cloudflare Access required: yes
- LAN break-glass: forbidden
- persistent bypass: forbidden
- source or merge authority does not create DNS, Tunnel routes, Access applications or policies

The installed publisher remains bound to loopback. The public Ausmalwiese web application remains a separate PUBLIC service and must not be routed through this ADMIN origin.

## Current source/runtime boundary

The ADMIN Cloudflare infrastructure cutover was completed and bounded verification was collected on 2026-10-21. Sanitized evidence established:

1. the publisher remained healthy on the reviewed loopback origin;
2. one exact-host self-hosted Access application exists with exact-owner allow semantics and no bypass;
3. the shared `rpi5-tunnel` carries the exact ADMIN hostname to the reviewed loopback publisher with Access protection required;
4. one proxied DNS record exists for the exact ADMIN hostname and public DNS resolution succeeds;
5. an anonymous browser is redirected to `Sign in · Cloudflare Access` instead of receiving ADMIN content;
6. the public `ausmalwiese.de` site remains anonymously reachable.

The hostname policy therefore records `audit_route_presence: present`.

The owner-authenticated browser path to the ADMIN page was intentionally not exercised because the verification authorization explicitly forbade login. This remains an evidence gap only; it is not authority to change Access, Tunnel, DNS, service or credential state.

## Current verification gate

Before making any future claim that the LIVE state is still current, collect fresh read-only evidence appropriate to that claim. If an owner-authenticated end-to-end browser verification is requested, it requires a separate explicit owner decision and must not expose owner identity, cookies or session material.

Any future Cloudflare, DNS, Tunnel, Access, service, credential or permission mutation remains separately exact owner-gated. Source merge does not authorize such changes.

## Evidence and privacy

Do not store owner email, account/tunnel/application/policy identifiers, Access AUD values, tokens, cookies or session material in GitHub evidence. Sanitized verification may report only hostname, trust/access classification, route-origin class, challenge/deny/pass result and boolean invariants.

## Non-authority

This document does not authorize Cloudflare, DNS, Tunnel, Access, firewall, service lifecycle, content publication, credential, secret or permission changes.
