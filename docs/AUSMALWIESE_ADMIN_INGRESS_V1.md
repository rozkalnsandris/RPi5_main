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

The publisher was installed and its loopback HTTP endpoint was verified on 2026-10-21. That dated evidence is sufficient to register the desired loopback ADMIN origin, but it is not proof that an external route or Access application exists now.

Until the separate LIVE cutover succeeds, the hostname policy records `audit_route_presence: absent`.

## Future LIVE cutover gate

A future exact owner authorization must bind the then-current `RPi5_main` SHA and the exact target `admin.ausmalwiese.de`. Before the first Cloudflare mutation, collect a fresh read-only preflight proving:

1. the publisher service is still healthy on the reviewed loopback origin;
2. the shared Tunnel is the intended delivery path;
3. no conflicting exact hostname route exists;
4. no conflicting or broader Access application would make the ADMIN hostname public or weaken unrelated hostnames;
5. the public `ausmalwiese.de` site remains outside this ADMIN policy;
6. the intended Access rule is exact-owner only, with no `Bypass` policy.

The bounded forward cutover is:

1. create the exact Tunnel/DNS route for `admin.ausmalwiese.de` to the loopback publisher;
2. create or reconcile one exact-host self-hosted Cloudflare Access application;
3. attach one exact-owner allow policy and no bypass;
4. verify unauthenticated external access is challenged or denied;
5. verify the authorized owner browser reaches the ADMIN page;
6. verify unrelated public Ausmalwiese endpoints remain anonymously reachable.

Any failure or ambiguity after mutation starts is STOP unless rollback/retry was explicitly included in that future authorization.

## Evidence and privacy

Do not store owner email, account/tunnel/application/policy identifiers, Access AUD values, tokens, cookies or session material in GitHub evidence. Sanitized verification may report only hostname, trust/access classification, route-origin class, challenge/deny/pass result and boolean invariants.

## Non-authority

This document does not authorize Cloudflare, DNS, Tunnel, Access, firewall, service lifecycle, content publication, credential, secret or permission changes.
