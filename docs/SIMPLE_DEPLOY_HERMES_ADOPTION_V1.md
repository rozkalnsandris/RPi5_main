# SIMPLE-DEPLOY Hermes existing-install adoption v1

Status: SOURCE-READY / NOT LIVE  
Issue: `RPi5_main#698`; post-merge baseline correction: `RPi5_main#708`

## Purpose

This source gate adds one dedicated adoption path for an already-installed Weather SIMPLE-DEPLOY host. It does not change `scripts/install-simple-deploy-v1.py` and does not turn the first-install path into an upgrade or repair mode.

The later LIVE operation is deliberately limited to two installed target deltas:

1. create `/etc/rozkalns-simple-deployer/compose/hermes-deals-api.yml` from the reviewed tracked adapter;
2. replace `/etc/rozkalns-simple-deployer/targets.json` with the reviewed two-target registry.

`/etc/rozkalns-simple-deployer/public_targets.json` is **not** a canonical SIMPLE-DEPLOY path. Issue #698 used that name in one requirement, but the installed executor and first installer both use `/etc/rozkalns-simple-deployer/targets.json`; the adoption path therefore rejects `public_targets.json` if it exists instead of creating a second registry.

## Reviewed baseline

The accepted Weather installation is a composite of unchanged Phase-A artifacts plus the completed Phase-B generated-identity refresh:

- repository: `rozkalnsandris/RPi5_main`;
- installed identity source SHA after the completed Phase-B repair: `7c6c7a8a80ca62d783c7f378b5865fae348a3fe9`;
- exact canonical installed identity SHA-256: `244abc1480a20937acb3d702760289631700aa27d0e518b454a7271dbd777df1`;
- Weather-only registry SHA-256, unchanged from Phase A: `c8b97e3274b732cdd0cdd2ddedb79515ebd9a6a433b094443594bdd8f74114ad`;
- Weather compose SHA-256, unchanged from Phase A: `80e2b47e4ed039c38285094e0b273fbc884f0a34ff34d8b201d8e93323af1f32`.

The earlier #698/#699 source text froze Phase-A identity `b57ed42d5eb01f15b62c1f53459ffe0539a57d9c`, but the separately authorized Phase-B post-install repair intentionally regenerated the installed identity and the completed Weather cutover continuity records `7c6c7a8a...` as the accepted corrected state. Issue #708 reconciles the Hermes adoption baseline to that real accepted installation without widening any mutation authority.

Before any staging write, `scripts/adopt-simple-deploy-hermes-v1.py` requires the fixed installed identity, Weather-only registry, Weather compose adapter and generic executor to be real root-owned regular files with their reviewed modes. The identity and Weather artifacts must match the exact baseline above. The Hermes compose destination, both fixed staging paths and the non-canonical `public_targets.json` name must be absent.

Any mismatch stops before mutation. There is no repair, cleanup, deletion, reinstall or fallback path.

## Reviewed desired state

The source checkout must be clean, correct-origin and exactly match the caller-provided reviewed source SHA. The source artifacts are fixed:

- registry: `ops/deploy/baselines/simple-deploy-targets-weather-hermes-v1.json`;
- Hermes adapter: `ops/deploy/simple-deploy-compose/hermes-deals-api.yml`.

The desired registry SHA-256 is `75660aefcf82bbc2b0b9d91cada515d9777804a7be2752f86d9d071c0ad9dbba` and its exact aliases are:

1. `rozkalns-weather-public-rpi5`;
2. `hermes-deals`.

The Weather registry entry must be semantically identical to the Weather-only baseline entry. The Hermes adapter SHA-256 is `644dc72da5dc13ee532dd29693db31358451669bb44de4df4b62c41736903f1c`.

## Mutation order and failure semantics

The entrypoint exposes only:

- `--expected-source-sha <exact full SHA>`;
- `--apply`.

There are no caller-selected paths, repositories, targets, commands, argv, environment, credentials or secret inputs.

A no-`--apply` invocation is preflight only and prints `SIMPLE_DEPLOY_HERMES_ADOPTION_PREFLIGHT_READY` on PASS.

A later separately authorized `--apply` uses only fixed same-filesystem staging names. Staging-file creation is the first authorized filesystem mutation and consumes that future LIVE authorization. The reviewed sequence is:

1. stage exact Hermes adapter bytes;
2. stage exact two-target registry bytes;
3. atomically publish the Hermes adapter without overwriting an existing destination;
4. revalidate the Weather-only registry;
5. atomically replace `targets.json`;
6. fsync the containing directories and verify exact postconditions.

After mutation has started, any error returns `SIMPLE_DEPLOY_HERMES_ADOPTION_FAILED` with bounded progress counters. There is no automatic retry, rollback or cleanup. A later recovery would require a new exact owner authorization.

Success requires:

- exact two-target registry;
- exact Hermes adapter bytes;
- unchanged Weather compose bytes;
- unchanged installed identity;
- unchanged generic executor bytes;
- no remaining fixed staging files.

## Explicit exclusions

This adoption path performs no Docker pull/up/reconcile, no systemd/service/timer mutation, no database/schema/data operation, no bind-data provisioning, no private Hermes config provisioning, no credential/secret operation, no Cloudflare/network change and no generic root shell.

Merge of this source does not authorize any RPi5 mutation. A future LIVE gate must freshly bind the then-current merged source SHA, installed baseline, private Hermes prerequisites and the exact adoption mutation envelope before `--apply`.
