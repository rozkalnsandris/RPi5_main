# Hermes Deals origin source provenance binding

Status: SOURCE-ONLY / RUNTIME-UNPROVEN  
Canonical mutable continuation: `RPi5_main#191`

This contract disambiguates the Hermes Deals origin broker source provenance after PR #369. It supersedes any earlier interpretation that treated `eligible_source_sha` as the current control-plane `main` SHA.

## Immutable implementation provenance

`eligible_source_sha=2550e77f6cb811ca6f10b49ef0b2fef554d64869`

That SHA is the merged PR #368 implementation baseline. It is immutable provenance for the reviewed broker/revalidator/host-evidence/helper-launch installation targets; it is **not** a claim about the current `RPi5_main/main` SHA and is not runtime evidence.

The manifest freezes these source-path Git blob identities:

| Source path | Git blob SHA |
|---|---|
| `ops/lib/deploy_executor/hermes_deals_origin_privileged_broker.py` | `2543278ee48f184a79ac67c70e7f77c06cfbd7c8` |
| `ops/lib/deploy_executor/hermes_deals_origin_source_auth.py` | `43640e9089cc39e96d472beb50e8653a5df5fa78` |
| `ops/lib/deploy_executor/hermes_deals_origin_helper_launch.py` | `5f190ebdcfdbc2a12242843733cb9740202cc9bd` |
| `ops/lib/deploy_executor/hermes_deals_origin_canonical_revalidator.py` | `8c5d9d7746248b485b212cf601786924ba6e4d42` |
| `ops/lib/deploy_executor/hermes_deals_origin_host_evidence.py` | `4358beb65a48ed72c82d0e99e1fc8fd49db88524` |
| `ops/lib/deploy_executor/hermes_deals_origin_broker_composition.py` | `a7a9421527fb5b2ed0f250446dc257f0a9ac8a29` |
| `ops/lib/deploy_executor/p9_source_auth.py` | `130fc36a22bb4ace500b022c3defcccbf0893012` |
| `ops/bin/rozkalns-hermes-deals-origin-broker` | `211b968b0c8ef6a0a7d73ce50a53d6bac7d2cc2f` |
| `ops/systemd/rozkalns-hermes-deals-origin-broker.socket` | `8eb05b83840b13b27e03e2bbb37d6d0bfc3697cb` |
| `ops/systemd/rozkalns-hermes-deals-origin-broker@.service` | `2a304e70550f17092b9cafd365bbf6d05d23893b` |

## Dynamic control-plane binding

`CONTROL_PLANE_SHA=RESOLVE_CURRENT_MAIN_AT_PREFLIGHT`

A runtime preflight must freshly resolve exact `rozkalnsandris/RPi5_main/main`; source does not hardcode that moving SHA. The preflight must fail closed unless:

1. the resolved current `main` is descendant-or-equal to the immutable PR #368 implementation baseline;
2. every installation target path above still resolves to its frozen Git blob SHA;
3. current exact-main CI and the current Hermes helper provenance are freshly revalidated;
4. the bounded runtime metadata/sanitization prerequisites pass without reading credential contents.

Any target blob mismatch means the implementation provenance is stale. A new reviewed source gate must establish a new immutable implementation baseline before runtime preflight or LIVE installation can proceed.

## Capability-specific installer source slice

The reviewed first-install entrypoint is `scripts/install-hermes-deals-origin-broker.py`, with its machine-readable source contract in `ops/deploy/hermes-deals-origin-broker-installer.json`.

`installer_source_blob=e020e547b7985e170758a39ff7b906c806c5052e`

The installer is deliberately narrower than generic privileged shell access:

- default invocation is read-only preflight; `--apply` requires root and a separate explicit LIVE owner authorization;
- it requires an exact checkout SHA supplied by the operator, proves that SHA is descendant-or-equal to the immutable implementation baseline, verifies its own tracked source at that SHA, and verifies all ten frozen install-target Git blobs;
- it checks only allowlisted runtime metadata: trusted root-owned parent directories, the fixed `rozkalns-deploy-executor` group, and source GitHub App credential **path/owner/group/mode only**;
- it never reads credential contents and never creates, replaces, chmods or otherwise mutates credentials;
- it is first-install-only: any pre-existing install target fails closed before mutation and requires a separate reconciliation source gate;
- its apply surface is exactly ten reviewed file materializations followed by `systemctl daemon-reload` and `systemctl enable --now rozkalns-hermes-deals-origin-broker.socket`;
- it does not directly start a broker service instance, run the Hermes helper, authorize a genuine audit, mutate App permissions, retire the runner, or enable the privileged dispatch path.

The installed broker entrypoint remains the reviewed fail-closed source stub. Socket activation therefore establishes only the broker transport boundary; it does **not** authorize or execute the later genuine origin audit canary.

The installer source does not convert source readiness into runtime readiness. `LIVE_INSTALL_ELIGIBLE` remains false until the installer slice is merged, exact-main provenance/CI is freshly rebound, and its bounded host preflight passes. A new exact-source LIVE authorization is required before `--apply`.

## Safety state

`INSTALLER_SOURCE_IMPLEMENTED=true`  
`SOURCE_READ_AUTHORITY_PROVEN=false`  
`BROKER_ENTRYPOINT_WIRED=false`  
`HELPER_PROCESS_LAUNCH_WIRED=false`  
`PRIVILEGED_DISPATCH_ENABLED=false`  
`HOST_WIRING_ENABLED=false`  
`LIVE_INSTALL_ELIGIBLE=false`  
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`  
`RUNNER_RETIREMENT_ELIGIBLE=false`  
`PRODUCTION_MUTATION_STARTED=false`

This document and its manifests prove source provenance only. They do not prove actual RPi5 services, files, permissions, credentials, App installation scope, replay storage, broker socket/service state, helper installation, deployed SHA, or production data.

After this source fix is separately merged, the next step is fresh merged-source CI/helper validation followed by the bounded **read-only installer preflight**. Any host installation/activation remains a separate explicit LIVE owner gate; one genuine audit canary and runner retirement remain later separate gates.
