# AdGuard DNS hardening — issue #788

This document defines the source-owned, fail-closed path for the DNS findings
recorded in `RPi5_main#788`. Source readiness is intentionally separate from
host/runtime readiness.

## Privacy and trust boundary

The preflight in `ops/bin/adguard-dns-preflight` is read-only by design. It
does **not** read or emit raw AdGuard configuration, DNS query logs, client
identities, container environments, Docker inspect output, credentials, or raw
network addresses. It emits only public-safe health booleans, AdGuard version,
listener presence, and resolver address classes.

The collector uses bounded metadata/behavior probes:

- default IPv4 route identity is used internally and is not emitted;
- the AdGuard process version and running-container name are checked without
  Docker inspect or environment reads;
- TCP/UDP port 53 listener presence is reduced to booleans;
- NetworkManager DNS addresses are reduced to classes such as `loopback`,
  `default_gateway`, `ipv4_public`, or `ipv6_link_local`;
- UFW DNS exposure is reduced to LAN/world allow booleans;
- ordinary DNS is probed through loopback AdGuard;
- the gateway PTR is queried directly and through loopback AdGuard, and only
  answer/no-answer booleans are retained.

A future runtime preflight still requires the applicable owner-authorized
read-only host scope. In particular, UFW metadata may require bounded `sudo`
read access; merge does not grant it.

## Why Phase 1 is separate

AdGuard Home uses `local_ptr_upstreams` for private reverse-DNS resolution.
When no explicit local PTR upstream is configured, AdGuard can derive local
resolvers from the operating system. That creates a correctness risk when the
host itself has public or router-advertised resolver paths.

The verifier `ops/bin/adguard-dns-preflight-verify` reaches `READY_PHASE1` only
when all of these are true:

1. collection itself reports PASS and proves no mutation or authorization use;
2. every privacy-boundary flag is false;
3. AdGuard is running with both TCP and UDP port 53 listeners;
4. ordinary DNS through loopback AdGuard answers;
5. the default gateway answers its own PTR query directly;
6. the same PTR query through AdGuard does not answer, behaviorally proving the
   targeted private-PTR defect;
7. UFW metadata is available and no world-wide allow rule for DNS is observed.

Parallel public resolver classes and IPv6 router-advertised resolver classes
are reported as later-phase facts; they do not widen Phase 1.

## Frozen Phase-1 mutation contract

`ops/contracts/adguard-private-ptr-phase1-v1.json` is source-disabled and
non-authorizing. A later explicit LIVE authorization is required after merge
and exact-main verification.

The future operation may perform **at most one** forward AdGuard API write:

- method: `POST`;
- endpoint: `/control/dns_config`;
- request body: partial update containing **only** `local_ptr_upstreams`;
- value: exactly one freshly verified default IPv4 gateway;
- every other DNS configuration key must be omitted;
- reading the protected full DNS configuration is not part of this operation;
- no container restart, Docker mutation, NetworkManager change, firewall
  change, router change, or alternate mutation path is allowed.

This one-field partial update follows AdGuard Home's DNS configuration API
model, where DNS settings are updated through `/control/dns_config`; the source
contract deliberately narrows the accepted request shape further than the
general API.

Authorization must bind the exact merged `RPi5_main` SHA, operation ID, target
alias, fresh preflight evidence identity, freshly verified gateway identity,
and the one-write limit. Authorization is consumed at the first configuration
write.

After the write, only bounded verification is permitted: the private gateway
PTR must answer through AdGuard, ordinary DNS must still answer through
AdGuard, and TCP/UDP port 53 listeners must remain present. Any error or
ambiguity after mutation starts means sanitized evidence plus STOP: no retry,
rollback, restart, cleanup, or alternate path.

## Later gates are intentionally separate

Phase 1 does not authorize or solve:

- RPi5 NetworkManager resolver cleanup or fallback policy;
- IPv6 RDNSS or Vodafone Ultra Hub DHCP/DNS advertisement;
- LAN-wide outbound DNS/DoT enforcement;
- AdGuard allowed-client/rate-limit hardening;
- Docker image pinning/container hardening;
- filter-list cleanup or telemetry changes.

Each item needs its own fresh evidence and owner decision because it crosses a
different runtime or network trust boundary.

## Upstream provenance reviewed

The Phase-1 field and API shape were checked against upstream AdGuard Home
sources for the observed stable release `v0.107.79`:

- tag commit: `AdguardTeam/AdGuardHome@05ba17b282da1c4393d6a4ba4db0cf519194a362`;
- `client/src/actions/dnsConfig.ts` sends only keys present in the supplied
  partial object and separately normalizes `local_ptr_upstreams`;
- the AdGuard Home API documents `POST /control/dns_config` and the optional
  `local_ptr_upstreams` DNSConfig field;
- the configuration reference states that an empty `local_ptr_upstreams`
  causes AdGuard Home to derive local resolvers from the OS.

These references establish source semantics only. Fresh runtime behavior is
still required before any later LIVE write.
