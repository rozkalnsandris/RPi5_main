# Cloudflare Zero Trust, mobile access, and cross-project audit — 2026-08-17

Status: **source-only audit / no production mutation**  
Tracking issue: #177  
Source baseline: `RPi5_main/main` at `ed5b238f4f662a8add394996431e9b5ea70210cc`

## 1. Purpose

This document is the public-safe canonical review of the Cloudflare footprint used by the RPi5 ecosystem and related projects. It reconciles the host-owned Cloudflare Tunnel, Access policy shape, origin exposure, application-side identity validation, mobile-owner access, availability, documentation drift, and the final defense-in-depth target.

This audit does **not** authorize any Cloudflare API write, DNS change, Access application/policy change, Tunnel route change, RPi5 host mutation, application deploy, or firewall mutation.

Sensitive values such as owner email addresses, home public IP addresses, account/tunnel IDs, Access audience tags, connector credentials, tokens, private recovery material, and exact private configuration are intentionally excluded.

## 2. Evidence boundary

The account-side state in this audit comes from the fresh GET-only production inventory captured on 2026-08-17 in `dashboard_RPi5` issues #107/#109. This audit did not independently mutate or re-query the Cloudflare account with privileged credentials.

Repository evidence reviewed includes:

- `RPi5_main/docs/V13_CLOUDFLARE_TUNNEL_OWNERSHIP_CONTRACT.md`;
- `RPi5_main/docs/V18_CLOUDFLARE_LAN_ORIGIN_AUDIT_CONTRACT.md`;
- `RPi5_main/docs/V19_DEALS_CLOUDFLARE_ROUTE_CUTOVER.md` and completed issue #61 evidence;
- `RPi5_main` Home Assistant issue #171;
- `dashboard_RPi5/ops/production/cloudflare-contract.json`;
- `dashboard_RPi5/docs/PHASE9B_CLOUDFLARE_ACCESS_OWNER_AUTH.md`;
- `dashboard_RPi5/docs/PHASE11C_CLOUDFLARE_LAUNCH.md`;
- `dashboard_RPi5/docs/MOBILE_SAMSUNG_A55.md`;
- `rozkalns-control-center/wrangler.jsonc` and Phase 3 Access/JWT docs;
- `rozkalns-cv/docker-compose.yml` and `rozkalns-cv/CLOUDFLARE.md`;
- `hermes-tech/docs/http-policy.json`;
- current Cloudflare documentation listed in section 12;
- community operational anecdotes listed separately in section 13.

## 3. Executive verdict

The architecture is fundamentally sound: the shared RPi5 connector is centralized, the tunnel is outbound-only, public CV/Tech origins are loopback-bound, Deals has completed its Cloudflare origin cutover to loopback, Home Assistant has a narrowed trusted-proxy production configuration, Dashboard has a strong deny-by-default target contract, and Control Center validates Access JWTs inside the Worker.

The largest remaining inconsistency is **Access policy scope**, not Tunnel transport. Fresh account evidence shows a broad parent application for `*.rozkalns.net` with both a home-network IP `BYPASS` and a two-user family `ALLOW`. This is inconsistent with the older mixed-zone design where some `rozkalns.net` hostnames are intentionally public and privileged/admin hostnames require stronger controls.

The target must therefore standardize **security invariants**, not force every project into an identical implementation. Tunnel-backed services, public static sites, and a Cloudflare Worker have different runtime architectures but should share the same trust-class rules.

## 4. Canonical trust classes

### PUBLIC

Examples: `rozkalns.net`, `tech.rozkalns.net`.

Required invariants:

- intentionally reachable without Access authentication;
- no router inbound port-forward;
- origin reachable by shared `cloudflared` through loopback only where technically possible;
- application/web security headers maintained;
- no broad Access wildcard may accidentally convert public sites into private sites;
- no public hostname may inherit an admin policy by accident.

### FAMILY_PRIVATE

Example: `deals.rozkalns.net` if family sharing remains intentional.

Required invariants:

- Access required;
- explicitly enumerated family identities or a deliberately scoped reusable family policy;
- no source-IP `BYPASS` as a convenience mechanism;
- origin tunnel-only/loopback where available;
- Access session behavior documented separately from ADMIN.

### ADMIN

Examples: Dashboard, Control Center, Hermes admin, Portainer, Grafana, Home Assistant, AdGuard Home, Uptime Kuma, Prometheus.

Required invariants:

- Access required and deny-by-default;
- exact owner identity for owner-only systems;
- no persistent IP `BYPASS`;
- Cloudflare One Client/WARP posture required for the owner-phone fast-access profile once verified;
- exact hostname Access app preferred for high-impact/mutating systems;
- `Protect with Access` for tunnel-backed origins where supported and proven;
- application-side JWT validation for privileged mutation surfaces when the app owns that boundary;
- LAN break-glass is an explicit recovery path, not the normal remote-access path;
- no public router inbound port-forward.

## 5. Cross-project consistency matrix

| Component / hostname class | Current evidence | Target | Verdict |
|---|---|---|---|
| Shared RPi5 `cloudflared` | Host-owned system service; app repos are forbidden from owning connector lifecycle | Keep `RPi5_main` as sole owner | PASS |
| `rozkalns.net` / CV | Actual compose binds web origin to loopback; stale `CLOUDFLARE.md` still describes retired app-owned tunnel container | Public + loopback + shared connector; retire stale instructions | IMPLEMENTATION PASS / DOC DRIFT |
| `tech.rozkalns.net` | Public-edge HTTP/security policy and central loopback origin contract | Public + loopback + no inherited admin Access | PASS subject to Access reconciliation |
| `deals.rozkalns.net` | #61 completed cutover and repeated verify evidence reports `LOOPBACK` + Access edge PASS | FAMILY_PRIVATE, loopback, explicit family policy | TRANSPORT PASS / POLICY RECONCILE |
| Home Assistant | #171 completed narrowed immediate trusted-proxy scope; remote Access and LAN break-glass both verified | ADMIN, exact policy, WARP posture, retain tested recovery | STRONG |
| Dashboard | Project contract requires exact hostname, one owner, no Bypass, Protect-with-Access, JWT validation for privileged terminal | Activate only after exact-app + tunnel + origin gates | TARGET STRONG / NOT YET PUBLIC |
| Control Center | Worker validates RS256 Access JWT, exact issuer/AUD/identity; parent wildcard can currently supply Access protection | Exact privileged Access app preferred; no broad Bypass | APP STRONG / EDGE POLICY RECONCILE |
| Portainer / Grafana / AdGuard / Kuma / Prometheus / Hermes admin | Central host contract classifies as ADMIN; some retain LAN break-glass origins | Exact/narrow ADMIN Access + no Bypass; preserve only deliberate LAN recovery | POLICY RECONCILE |

## 6. Fresh account-side drift discovered on 2026-08-17

The fresh GET-only inventory in `dashboard_RPi5` #107/#109 records:

- four Access applications total at that moment;
- no exact Dashboard Access application yet;
- a broad `homelab-private` application covering `*.rozkalns.net`;
- a long session duration on that wildcard application;
- one home-network source-IP `BYPASS` policy;
- one family `ALLOW` policy containing two exact identities.

This is not an emergency exposure by itself, because Access remains deny-by-default for requests that do not match an Allow/Bypass rule. However, the wildcard is too broad as a canonical long-term policy boundary because the same DNS zone contains PUBLIC, FAMILY_PRIVATE, and ADMIN services.

Cloudflare explicitly documents that `BYPASS` disables Access security controls and Access logging for matching traffic, and recommends against using Bypass as persistent access to internal applications. Therefore the home-IP Bypass must not be the owner convenience mechanism for ADMIN applications.

### Required reconciliation

1. Inventory every current Access application, domain/path, policy, action, identity selector, session duration, posture rule, and audience tag with GET-only API calls.
2. Prove which exact hostnames currently inherit the parent wildcard and whether any more-specific applications override it.
3. Create an explicit desired-state plan from `ops/contracts/cloudflare-hostname-policy.yaml`.
4. Remove broad/high-impact Bypass only in a separately authorized, bounded write after phone/WARP access has been proven.
5. Do not enable account-wide `Require Access protection` until all intended PUBLIC hostnames are modeled or explicitly exempted; otherwise public sites can be blocked.

## 7. Owner phone: Wi-Fi + mobile data without repeated login

### Do not bind the phone by MAC address

MAC binding is the wrong layer for this requirement. A MAC address identifies a link-layer interface on a local network; it is not a stable Internet identity that Cloudflare can use when the phone moves to 4G/5G. Modern mobile operating systems can also randomize Wi-Fi MAC addresses. A MAC-based design would therefore neither solve cellular access nor provide the desired Zero Trust identity.

Cloudflare's supported model is device enrollment through Cloudflare One Client plus identity/session and device-posture policy.

### Recommended Samsung A55 profile

1. Install **Cloudflare One Agent** on Android.
2. Enroll it into the Zero Trust organization using a narrowly-scoped device-enrollment policy that allows only the owner identity.
3. Keep the client connected/auto-connected.
4. Enable **Authenticate with Cloudflare One Client** for the ADMIN Access applications after testing.
5. Require the **Require WARP** posture signal for ADMIN access.
6. Optionally require a supported Android minimum OS version as a second posture condition.
7. Start with a **30-day Cloudflare One Client session** for the single owner phone if the convenience/security tradeoff is accepted. This means normal browsing from the enrolled phone can remain silent across Wi-Fi and mobile data until the device-client session expires or is revoked.
8. Keep application/policy sessions shorter where useful; Cloudflare can refresh an expired app token without an IdP prompt while a valid higher-level session remains. When Cloudflare One Client authentication is enabled, the valid client session takes precedence for reauthentication.
9. Preserve normal phone screen lock/biometric protection and define a lost-phone procedure that revokes the enrolled device/user session before any other recovery action.

### Why `Require WARP`, not Device UUID, is the initial posture gate

Cloudflare supports Android posture checks for `Require WARP`, `Require Gateway`, OS version, and Device UUID. However, Device UUID values must be assigned through managed deployment/MDM and cannot be assigned manually. For one personal Android phone, `Require WARP` + exact owner identity is the simpler supported first step. Device UUID can be added later if an MDM-managed device model is introduced.

### Human access must not use a service token

Service tokens are appropriate for machine-to-machine authentication, not for making a human browser silently privileged. The owner-phone path must remain attributable to the owner identity and enrolled device posture.

## 8. Origin and application defense in depth

### Tunnel-backed applications

For ADMIN tunnel-backed HTTP services, verify the route's Access protection fields and do not assume that the existence of an Access application alone proves origin protection. The fresh Dashboard preflight correctly treated missing/unproven `originRequest.access` values as a blocker rather than guessing.

Use `Protect with Access` where supported and keep application-side JWT verification for privileged surfaces that already own an authorization boundary. JWT verification must validate signature plus expected issuer/audience/identity/expiry; checking a header's presence is insufficient.

### Worker-backed Control Center

Control Center does not use the RPi5 origin path, so it should not copy the tunnel implementation. Its correct invariant is:

- Access at the edge;
- Worker verification of the Access application JWT signature and exact issuer/AUD/owner claims;
- no cookie-only or header-presence shortcut;
- separate authorization for GitHub mutations;
- secrets outside source control.

### Public origins

The CV and Hermes Tech pattern is the preferred public-site origin model: shared tunnel plus loopback-bound service, without a LAN/public listening requirement. CV's code is already in this shape; only its stale Cloudflare documentation needs to be retired in its own repo.

## 9. Availability and recovery

The current connector has four active Cloudflare edge connections, which is healthy edge-path redundancy. It is **not** host redundancy: if the RPi5, its network interface, power, or the single `cloudflared` service fails, all host-owned tunnel routes fail together.

Cloudflare documents tunnel replicas and recommends two dedicated hosts per location as its baseline. The target therefore includes a second physical `cloudflared` replica on a separate failure domain. That replica must use the same remotely managed tunnel and must not weaken the single-owner configuration contract.

Additional operational controls:

- keep the connector metrics endpoint on loopback;
- alert on connector/service failure and loss of healthy tunnel connections;
- keep critical ingress updates controlled and reversible rather than relying on an unattended updater that can remove the sole remote-access path;
- retain a tested LAN break-glass route for selected ADMIN services;
- retain an off-device recovery path so a tunnel/container failure does not make the host administratively unreachable.

## 10. Prioritized hardening roadmap

### P0 — policy correctness before convenience rollout

- [ ] GET-only full Access app/policy inventory and exact-host resolution proof.
- [ ] Reconcile the broad `*.rozkalns.net` app against PUBLIC/FAMILY_PRIVATE/ADMIN classes.
- [ ] Prove `tech.rozkalns.net` remains intentionally public and is not accidentally governed by an inherited private policy.
- [ ] Define exact Dashboard and Control Center privileged application policy shapes.
- [ ] Prove `Protect with Access` state for every tunnel-backed ADMIN route where it is expected.
- [ ] Enroll the owner Android phone and verify WARP posture without changing existing production policy.

### P1 — separately authorized security improvement

- [ ] Create exact/narrow ADMIN Access apps and owner-only policies.
- [ ] Enable `Require WARP` for the owner-phone ADMIN policy after a canary proves Wi-Fi and 4G/5G access.
- [ ] Enable `Authenticate with Cloudflare One Client` for selected ADMIN applications and validate session behavior.
- [ ] Remove the broad home-IP Bypass from ADMIN reachability only after the enrolled-device path and rollback path are proven.
- [ ] Split FAMILY_PRIVATE policy from ADMIN policy.
- [ ] Retire the stale `rozkalns-cv/CLOUDFLARE.md` app-owned tunnel instructions in the CV repo.
- [ ] Add a second physical `cloudflared` replica and verify failover without changing application origins.

### P2 — continuous assurance

- [ ] Add a scheduled **read-only** drift audit comparing remote Tunnel/Access state to the canonical registry.
- [ ] Alert if a new hostname appears without an explicit trust class.
- [ ] Alert if any ADMIN app gains `BYPASS`, `Everyone`, broad email-domain access, or loses required device posture.
- [ ] Alert if a PUBLIC origin is no longer loopback-only where loopback is the contract.
- [ ] Periodically test recovery from a stopped primary connector using the second replica / break-glass path.
- [ ] Revisit optional account-wide `Require Access protection` only after PUBLIC exemptions/applications are deliberately modeled.
- [ ] Consider a future dedicated admin namespace (for example, a deliberately structured admin subdomain hierarchy) if hostname migration cost is acceptable; this would make narrow wildcard grouping safer than today's mixed `*.rozkalns.net` namespace.

## 11. Future production-change gate

Any later Cloudflare mutation must follow the existing owner workflow:

1. exact source/contract baseline;
2. GET-only account/Tunnel/Access inventory;
3. fail closed on missing/ambiguous application, route, policy, audience, or identity evidence;
4. write a bounded mutation plan and rollback plan;
5. obtain separate explicit owner authorization for the exact mutation;
6. apply only the authorized object/fields;
7. re-read through the Cloudflare API and prove unrelated objects are unchanged;
8. independently verify:
   - owner phone on home Wi-Fi;
   - owner phone on cellular data;
   - unauthenticated/non-enrolled client denial for ADMIN;
   - PUBLIC sites remain public;
   - LAN break-glass remains available where intended;
   - application-level JWT/health checks pass;
9. rollback immediately if the required invariants are not all proven.

No step in this document grants authorization to execute that gate.

## 12. Primary sources — Cloudflare documentation

- Access policies and Bypass semantics: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/
- Common Access policies: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/common-policies/
- Cloudflare One Client sessions: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/client-sessions/
- Access session management: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- Access authorization cookies / global SSO token: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/
- Access application token and origin validation: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/
- JWT validation: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- Cloudflare One Client manual Android deployment: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/manual-deployment/
- Device enrollment permissions: https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/device-enrollment/
- Cloudflare One Client posture checks: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/
- Device UUID posture requirements: https://developers.cloudflare.com/cloudflare-one/reusable-components/posture-checks/client-checks/device-uuid/
- Require Access protection: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/require-access-protection/
- Tunnel replicas / HA / firewall model: https://developers.cloudflare.com/tunnel/configuration/
- Tunnel system requirements and two-host baseline: https://developers.cloudflare.com/tunnel/downloads/system-requirements/

## 13. Community operational signals — non-authoritative

Community posts were reviewed only as operational experience, never as the source of security policy. A recent r/selfhosted failure report describes an unattended container updater removing the Cloudflare Tunnel and other management containers, leaving the operator without the expected remote-access path. The useful lesson for this environment is consistent with our existing workflow: keep the ingress connector host-owned, avoid unbounded unattended mutation of critical ingress, keep configuration in Git, and maintain an independent recovery path.

Reference: https://www.reddit.com/r/selfhosted/comments/1salkni/laugh_at_my_pain_and_learn_from_my_mistakes/

Other self-hosting discussions repeatedly converge on the same broad operational pattern: do not expose raw router ports merely for convenience; put authentication/identity in front of private web applications; separate administrative trust from family/public access; and retain recovery access. These are treated as anecdotes/checks against the design, while Cloudflare's documentation remains authoritative.

## 14. Final security conclusion

Do **not** solve owner convenience by trusting a MAC address, a home source IP, a browser-stored service token, or a broad wildcard Bypass.

The strongest practical target for this environment is:

**exact owner identity + enrolled Cloudflare One Client on the phone + `Require WARP` posture + long but revocable client session + exact/narrow ADMIN Access apps + no persistent Bypass + shared host-owned Tunnel + loopback origins where possible + application JWT verification on privileged mutation boundaries + second physical Tunnel replica + tested LAN/off-device recovery.**

That design provides the requested near-frictionless phone access on both Wi-Fi and mobile data without turning the ADMIN surface into a network-location trust model.