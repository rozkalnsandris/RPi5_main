# Control Phase 5 RPi5 production visibility source contract

This source-only contract is bound to the reviewed Control consumer at `rozkalnsandris/rozkalns-control-center@1da96b628054a32c79cc6e2f201f5a4a5036c12c`, path `src/shared/production-visibility.ts`, blob `5546c0fb37072c5903d6e7c6aa02a9eea7baf43d`.

`ops/lib/deploy_executor/control_phase5_production_visibility.py` emits only the consumer's ten sanitized fields, rejects extra/missing fields, requires an exact expected project/repository/main SHA, applies the same 5-minute freshness window and contradiction/blocker rules, and fails closed on consumer-provenance drift.

## Signed delivery source boundary

The reviewed Control transport at the same Control main is `src/shared/rpi5-observation-transport.ts`, blob `cae7864f9a1053b5141353ac192c9c2d512f955a`. `ops/lib/deploy_executor/control_phase5_observation_transport.py` mirrors that v1 byte contract without opening a runtime transport path.

The producer serializes the already-normalized ten-field payload in the reviewed field order as compact UTF-8 JSON and signs an exact byte sequence:

```text
rozkalns-control-center.phase5.rpi5-production-visibility.v1\n
control-phase5-rpi5-observation-v1\n
<deliveryId>\n
<sentAt>\n
<keyId>\n
<payload-byte-length>\n
<exact payload bytes>
```

The source contract requires the same lowercase UUIDv4 delivery identity, canonical millisecond UTC timestamp, bounded `keyId`, 16 KiB payload limit and five-field metadata envelope (`version`, `deliveryId`, `sentAt`, `keyId`, `signature`) expected by Control. The 64-byte signer result is encoded as unpadded base64url, matching the Control verifier's 86-character Ed25519 signature representation.

Signing is deliberately dependency-injected: the module accepts only a callable that receives the exact signing bytes and returns exactly 64 bytes. It does not load a key, name a key path, provision or rotate credentials, select a runtime secret source, open a socket, send HTTP, or acquire production evidence. The signer interface is therefore a source contract, not runtime signing authority.

Current Cloudflare Workers Web Crypto documentation supports standard `Ed25519` through `crypto.subtle`, and the Control verifier uses the standard algorithm over the exact supplied binary data. The source contract intentionally does not introduce the legacy `NODE-ED25519` variant.

## Non-authority

These modules acquire no production evidence and grant no SSH, sudo/root, protected-filesystem, runtime, credential, database, Queue, Worker, Cloudflare, network or mutation authority. A generated signed delivery is observational evidence only and grants no deploy, rollback, database or host authority.

Actual private-key provisioning/access, signer implementation, protected-host evidence acquisition and delivery to Control remain later separately reviewed STRICT/LIVE gates. Source merge is not LIVE authorization and does not prove current RPi5 runtime state or Control deployment state.
