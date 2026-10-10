# Phase 8 ingress operations and recovery

Status: **SOURCE-ONLY operating guide — no standing LIVE authority**  
Roadmap: `RPi5_main#60` Phase 8  
Source outcome: `RPi5_main#951`  
Policy source: `ops/contracts/ingress-registry-v1.json`

## Scope and provenance

This is the single navigation point for ingress ownership, failure classification and
recovery **decisions**, not an executable recovery procedure. The machine registry and
its source documents remain authoritative. An old audit result is not proof of current
runtime configuration. No step below authorizes mutation of the host, containers,
systemd, firewall, credentials, Cloudflare or DNS.

The owner-authorized, sanitized Phase 7 audit snapshot dated **2026-10-10** on
`RPi5_main@2f0f0ed3ff6fd8b9426c2ce252009a778d315bc4` reported
`PASS` for 13 registered services, Cloudflare routes and connector health, with
`mutation_performed=false`. Evidence: roadmap #60 comment
[6094639909](https://github.com/rozkalnsandris/RPi5_main/issues/60#issuecomment-6094639909).
It supersedes an earlier Weather `DRIFT` **observation**, but does not establish
who changed the runtime, how, or whether the pass persists.

## Canonical matrix: PUBLIC / ADMIN / PRIVATE

Do not duplicate a hand-maintained service inventory here. Read
`docs/INGRESS_REGISTRY_V1.md` and `ops/contracts/ingress-registry-v1.json`
for each public service identifier, zone, repository/runtime owner, intended origin
class, Access requirement, firewall expectation, allowed LAN break-glass and
`recovery_ref`. Every tracked service belongs to exactly one zone.

| Zone | Intended edge trust | Origin and emergency access |
| --- | --- | --- |
| PUBLIC | Anonymous HTTP; **no Cloudflare Access** | Reviewed loopback origin, no default LAN break-glass. Follow `docs/INGRESS_PUBLIC_ZONE_VERIFICATION_V1.md`. |
| ADMIN | Exact administrator Access policy | Retain only registry-authorized LAN break-glass. Do not assume every ADMIN listener should become loopback. Follow `docs/INGRESS_ADMIN_ZONE_VERIFICATION_V1.md`. |
| PRIVATE | Separate private Access audience; never inherit ADMIN or PUBLIC | Reviewed private service origin and recovery boundary. Follow `docs/INGRESS_PRIVATE_ZONE_VERIFICATION_V1.md`. |

The host-owned shared Tunnel belongs to `RPi5_main`, not an application
repository. The interface and ownership contract is
`docs/V13_CLOUDFLARE_TUNNEL_OWNERSHIP_CONTRACT.md`.
Application repos own their app release, not shared Tunnel mutation or its
credentials. Existing app-specific `recovery_ref` entries in the registry take
precedence over a generic fallback.

## Decision tree: inspect → classify → separate authority

1. **Observe source:** Resolve fresh `main`, exact checks, source/installed
   operator provenance and the intended registry policy. GitHub source alone
   does **not** prove installed runtime or Cloudflare state.
2. **Observe runtime only inside its own scoped owner read-only gate:** Use the
   reviewed, protected Phase 7 operator and
   `docs/INGRESS_DRIFT_AUDIT_V1.md`; accept only bounded sanitized
   `PASS`, `DRIFT` or `BLOCKED` evidence. No secret, private address,
   internal port, raw rule, log or session material may be published.
3. **If PASS:** record the exact source SHA and evidence date. Do not claim
   durable availability or close unrelated operational work merely from one
   snapshot.
4. **If DRIFT:** identify the specific service and class; keep unaffected zones
   unchanged. Plan preflight, previous-good recovery reference, change scope,
   post-verification and owner LIVE decision **before** any corrective write.
   Recheck external behavior only under its separate authorized gate.
5. **If BLOCKED:** preserve sanitized reason codes and stop; obtain missing
   execution capability/evidence instead of bypassing protected boundaries,
   retrying consumed authorization or using an unreviewed alternate path.

## Connector failure / restoration

The shared connector lifecycle and credential boundary belong to
`docs/V13_CLOUDFLARE_TUNNEL_OWNERSHIP_CONTRACT.md` and
`docs/CLOUDFLARE_TUNNEL_OPERATOR_V1.md`. Determine whether failure is
connector service state, edge-connection drift or a remotely managed route
disagreement using scoped read-only evidence. **Do not** restart the connector,
reinstall it, rotate a token or replace protected configuration as a diagnostic
shortcut. A recovery action needs its own exact source/target, authorized
mutation class, baseline, recovery semantics and post-verification.

## Route-change rollback

For a failed or unexpected Tunnel route, distinguish **edge route origin
class** from **host listener/Docker publish class** using the Phase 7 evidence
contract. Confirm the single intended public hostname and its zone in the
registry before planning any update. A rollback proposal must name a
previously reviewed route revision, prove its external Access semantics and
origin expectation, preserve unrelated routes, and bind a **separate
Cloudflare LIVE authorization**. A prior source merge or read-only pass is not
rollback authority. Do not print or store raw Cloudflare configuration in Git.

## ADMIN LAN break-glass and PRIVATE recovery

For ADMIN, read the service's registry `lan_break_glass` and
`firewall_expectation` along with
`docs/INGRESS_ADMIN_ZONE_VERIFICATION_V1.md`. Deliberately approved LAN
access is **not** an accidental bypass merely because a listener is not
loopback. Verify external Access independently; never weaken Access or expose
LAN/wildcard Docker publishing to recover a login path.

For PRIVATE, consult `docs/INGRESS_PRIVATE_ZONE_VERIFICATION_V1.md` and
the service-specific `recovery_ref`. PRIVATE access is distinct from ADMIN;
the authorized-private acceptance surface remains a separately protected
gate. Never substitute a temporary public bypass, generic ADMIN grant or
unverified direct-origin exposure.

## Reboot-survival and final acceptance gate — NOT RUN HERE

A future **separately authorized** reboot-survival acceptance should establish
a baseline of connector and registered app state, preserve required recovery
references, then verify after the actual host reboot: connector active/enabled,
expected edge connections, PUBLIC anonymous path, ADMIN/PRIVATE Access
semantics, listener/Docker/firewall classes and a fresh 13-service Phase 7
report. The reboot and any service lifecycle changes are **LIVE**, and cannot
be performed under this source-documentation outcome. A documentation link
or previous PASS does not satisfy this real reboot gate.

## Separate SIMPLE-DEPLOY scheduler gate

The 2026-10-10 sanitized systemd snapshot recorded
`rozkalns-simple-deployer.timer` as `enabled/inactive/dead`,
while `rozkalns-weather-public-ingest.timer` was
`enabled/active/waiting`. This is **not** a Phase 7 ingress drift code,
but SIMPLE-DEPLOY scheduled reconciliation remains unverified.
`enabled` and `active` are different systemd states: **do not infer
operation from enablement**. Diagnose its intended activation policy,
fresh state and any blockers through an independently scoped read-only
gate; starting/restarting/resetting a timer or service requires separate
owner LIVE authority and verification.

## Source safety and references

- Production deploy/change required for this source-only guide: **NO**.
- No Docker/Compose apply, systemd lifecycle, Cloudflare/DNS, firewall,
  credential, permission, repository-setting or protected runtime mutation
  is included in `#951`.
- Owner MERGE authorization is separate; merge does not authorize LIVE.
- Historic incident and Phase 7 snapshots are evidence, never future
  authorization or automatic runtime truth.
- Validate existing recovery ownership under `docs/DISASTER_RECOVERY.md`;
  cross-service recovery must not silently rewrite individual app contracts.

Official documentation:
- [Docker port publishing](https://docs.docker.com/engine/network/port-publishing/)
- [systemd systemctl states](https://man7.org/linux/man-pages/man1/systemctl.1.html)
