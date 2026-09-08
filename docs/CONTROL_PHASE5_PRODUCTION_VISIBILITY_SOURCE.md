# Control Phase 5 RPi5 production visibility source contract

This source-only contract is bound to the reviewed Control consumer at `rozkalnsandris/rozkalns-control-center@d481e210aea0f2838547622c7471c381dcbdd467`, path `src/shared/production-visibility.ts`, blob `5546c0fb37072c5903d6e7c6aa02a9eea7baf43d`.

`ops/lib/deploy_executor/control_phase5_production_visibility.py` emits only the consumer's ten sanitized fields, rejects extra/missing fields, requires an exact expected project/repository/main SHA, applies the same 5-minute freshness window and contradiction/blocker rules, and fails closed on consumer-provenance drift.

It acquires no production evidence and grants no SSH, sudo/root, protected-filesystem, runtime, credential, database, Queue, Worker, Cloudflare, network or mutation authority. Actual RPi5 observation/transport remains a later separately reviewed read-only slice. Source merge is not LIVE authorization.
