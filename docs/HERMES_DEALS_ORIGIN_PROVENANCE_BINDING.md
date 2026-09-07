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

`installer_source_blob=3edabde4660b04539c808a806e1bf1bcc8fefef8`

The installer is deliberately narrower than generic privileged shell access:

- default invocation is read-only preflight; `--apply` requires root and a separate explicit LIVE owner authorization;
- it requires an exact checkout SHA supplied by the operator, proves that SHA is descendant-or-equal to the immutable implementation baseline, verifies its own tracked source at that SHA, verifies nine frozen broker-owned install-target Git blobs, and separately verifies the frozen `p9_source_auth.py` shared-prerequisite source blob;
- root-side Git provenance uses only command-scoped `safe.directory=<exact resolved REPO_ROOT>` while preserving the fixed minimal subprocess environment; wildcard trust and root global/system Git config mutation are forbidden;
- it checks only allowlisted runtime metadata: trusted root-owned parent directories, the fixed `rozkalns-deploy-executor` group, and source GitHub App credential **path/owner/group/mode only**;
- it never reads credential contents and never creates, replaces, chmods or otherwise mutates credentials;
- it is first-install-only for broker-owned targets: any pre-existing broker install target still fails closed before mutation; the already-owned P9 `p9_source_auth.py` dependency is not adopted or overwritten and is instead an exact existing shared prerequisite;
- shared-prerequisite validation is read-only and descriptor-safe: regular non-symlink `root:root 0644`, `O_RDONLY|O_NOFOLLOW|O_CLOEXEC`, exact reviewed bytes/blob, and stable device/inode identity are mandatory; the broker installer never chmods/chowns/replaces that dependency;
- its apply surface is exactly nine reviewed broker file materializations followed by `systemctl daemon-reload` and `systemctl enable --now rozkalns-hermes-deals-origin-broker.socket`; the shared prerequisite is revalidated immediately before systemd activation;
- it does not directly start a broker service instance, run the Hermes helper, authorize a genuine audit, mutate App permissions, retire the runner, or enable the privileged dispatch path.

The installed broker entrypoint remains the reviewed fail-closed source stub. Socket activation therefore establishes only the broker transport boundary; it does **not** authorize or execute the later genuine origin audit canary.

The installer source does not convert source readiness into runtime readiness. `LIVE_INSTALL_ELIGIBLE` remains false until the installer slice is merged, exact-main provenance/CI is freshly rebound, and its bounded host preflight passes. A new exact-source LIVE authorization is required before `--apply`.

## Credential prerequisite discovered by the first bounded preflight

After PR #371 merged, fresh exact-main checks and Hermes helper provenance were revalidated and one default-mode installer preflight was executed on trusted `rpi5` at exact clean checkout `32655619fca01105f872a4a2c44c41edc373b4dd`.

It failed closed before mutation because the fixed source GitHub App credential target was absent. The public-safe receipt recorded:

- `result=FAIL_CLOSED`;
- `credential_content_read=false`;
- `credential_mutated=false`;
- `helper_executed=false`;
- no installer `--apply`, systemd action, broker install or other host mutation occurred.

Canonical public-safe continuity receipt: `RPi5_main#191` comment `5551180411`.

This proves only that credential placement is the current prerequisite. It does **not** authorize credential creation and it does not prove any secret value or credential validity.

## Capability-specific source credential provisioner

Issue #372 adds a separately reviewable first-install-only source provisioner:

`scripts/provision-hermes-deals-origin-source-credential.py`

`credential_provisioner_source_blob=76692cadd7a2dd959a5777f0978bb16371e7e0be`

The provisioner contract is intentionally narrower than generic file or secret placement:

- exact reviewed `RPi5_main` checkout SHA is required and revalidated immediately before mutation;
- root-side Git provenance uses only command-scoped `safe.directory=<exact resolved REPO_ROOT>`; wildcard trust and root global/system Git config mutation are forbidden;
- the credential value is accepted only through hidden multiline `/dev/tty` input with terminal echo disabled; it is never accepted through argv, environment variables, GitHub, chat, stdout or stderr;
- the downloaded PEM is not staged as an intermediate plaintext file on RPi5; keep the workstation copy protected and enter it only into the reviewed hidden TTY prompt for first-install placement;
- only the two reviewed ASCII-armored private-key PEM envelopes are accepted, with bounded input size and canonical base64-text body checks;
- target is fixed to `/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem`, `root:root 0600`;
- its parent credential directory is fixed to `/etc/rozkalns-hermes-deals-origin-broker`, `root:root 0700`;
- existing credential target fails closed; overwrite and rotation are not authorized;
- file creation requires `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`;
- maximum mutation surface is one credential-directory creation if absent plus one credential-file creation;
- mutation entry is recorded before the first filesystem create attempt; any later error is terminal STOP with no retry, rollback or cleanup;
- it performs no GitHub API request, token mint, App permission/repository-selection mutation, broker install, helper/audit execution or systemd action.

This source provisioner does not itself authorize placement. Credential placement remains STRICT and requires a separate exact-source owner LIVE authorization. No credential value may appear in GitHub, chat or public evidence.


### First LIVE placement attempt — pre-mutation source-trust failure

The first owner-authorized credential-placement invocation after #376 failed closed with `reason=source SHA mismatch` and `mutation_started=false` before credential input or filesystem creation. The unprivileged wrapper had already matched exact main and the provisioner blob. Source review identified the root-side cause: the provisioner's intentionally minimal Git subprocess environment removed Git's documented `SUDO_UID` ownership exception, so root Git could reject the user-owned checkout before provenance commands completed. Issue #377 corrects this without widening environment trust: Git receives only command-scoped `safe.directory=<exact resolved REPO_ROOT>`. No retry is authorized by this source correction.

### Second LIVE placement attempt — pre-mutation TTY I/O failure

After #379 merged and a clean exact-source worktree was prepared, the next owner-authorized credential-placement invocation failed closed before credential input or filesystem creation with `io.UnsupportedOperation: File or stream is not seekable` and `mutation_started=false`. The terminal itself was a valid PTY (`/dev/pts/2`). Source review identified `open("/dev/tty", "r+")` as the cause: Python update-mode buffered I/O requires a seekable raw stream, while a TTY is non-seekable. Issue #381 replaces that stream with separate read-only and write-only `/dev/tty` text streams while preserving echo suppression/restoration and every existing credential safety boundary. This remains pre-mutation evidence only and does not authorize a placement retry.

### Broker installer preflight after credential placement — pre-mutation source-trust failure

After the source credential first-install step, the owner ran the default-mode broker installer preflight at exact `RPi5_main` SHA `750736eb681f15184358f3c8c7e18f46f47dc99c`. It failed closed before installer mutation with `reason=reviewed Git source validation failed`. Credential contents were not read or mutated and the Hermes helper was not executed.

Source review identified the same root-side Git ownership class already corrected for the credential provisioner: the installer's intentionally minimal subprocess environment omits Git's documented `SUDO_UID` sudo ownership exception, while installer Git commands did not provide an exact `safe.directory`. Issue #383 corrects only that provenance invocation by adding command-scoped `safe.directory=<exact resolved REPO_ROOT>` to every installer Git command. Wildcard trust, root global/system Git config mutation, environment widening and installer mutation-surface changes remain forbidden.

This failure is pre-mutation evidence only. It does not authorize a preflight retry, broker installation, systemd activation, helper execution or genuine audit.

### Accepted credential placement and merged installer repair

Canonical `RPi5_main#191` records that the later separately owner-authorized credential first-install at exact `750736eb681f15184358f3c8c7e18f46f47dc99c` completed with public-safe result `HERMES_SOURCE_CREDENTIAL_PROVISIONED`, `mutation_started=true`, and no credential content emitted. That one-shot authorization is consumed/non-reusable. This source document does not independently re-read or prove the credential's current protected runtime state.

PR #384 subsequently merged the narrow installer Git-trust repair. At the audited checkpoint, current `RPi5_main/main=05fb1254307ec3eb91fb7d16ff1c242d585c53a8`, exact-main checks are 5/5 SUCCESS, installer source blob is `6762f6dffa7908cc8e8dd8fb7c144c1433edbe54`, and provisioner blob remains `76692cadd7a2dd959a5777f0978bb16371e7e0be`. The trusted checkout audit remained clean/detached at old source `750736eb...`; no fetch, merge, reset, rebase, stash or clean was performed by that audit.

### Post-convergence broker preflight — existing P9 shared target

After PR #385 merged and the separately owner-authorized trusted checkout convergence completed, one fresh default-mode broker installer preflight was run at exact `RPi5_main/main=6264113026bf5842edb5b45bb13fd2b3b513dc73`. It failed closed before broker mutation because `/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py` already existed. The public-safe receipt recorded `credential_content_read=false`, `credential_mutated=false`, `helper_executed=false` and no `--apply` or systemd action. Minimal follow-up metadata established exactly one pre-existing reviewed target, `root:root 0644`; that failed run did not read its contents.

This source reconciliation does **not** authorize overwrite or adoption. `p9_source_auth.py` is reclassified as an external shared runtime prerequisite already owned by the P9 installation path. Broker preflight must prove its exact reviewed source identity (`130fc36a22bb4ace500b022c3defcccbf0893012`) through a bounded descriptor-safe read plus exact owner/group/mode and inode/path stability. The broker installer mutation set is reduced to the remaining nine capability-specific files, all still `O_EXCL` first-install targets. Any missing, metadata-drifted, byte-drifted or replaced shared prerequisite fails closed; any pre-existing broker-owned target also still fails closed.

This is source readiness only. The observed runtime metadata is historical evidence for the failed preflight and is not a claim that the shared prerequisite will still match after this source change merges.

### Broker preflight after shared-prerequisite source reconciliation — reviewed runtime blob is capability-stale

After PR #386 merged and the trusted checkout converged to exact `475aa1c935868d0ac7a5cb5569e051767faab643`, the owner ran one fresh default-mode broker installer preflight under root without `--apply`. It failed closed because the installed shared prerequisite content did not equal the required reviewed blob. The receipt explicitly preserved `credential_content_read=false`, `credential_mutated=false` and `helper_executed=false`; no broker/systemd/credential mutation occurred.

Minimal read-only follow-up identified the installed shared file as `root:root 0644`, Git blob `4cb441873df8245387f06ee55d637a9f7b11cdc8`. Repository history binds that blob to the earlier reviewed Gate-D P9 source-auth implementation. Current source blob `130fc36a22bb4ace500b022c3defcccbf0893012` is the later #365/#366 capability extension that adds the exact `rozkalnsandris/hermes-deals` repository binding. Therefore the old runtime blob must not be accepted as an equivalent prerequisite: it is reviewed but does not implement the Hermes source-read capability required by this broker path.

The source-only correction adds `scripts/install-deploy-executor-p9-hermes-source-auth-upgrade.py` with machine contract `ops/deploy/p9-hermes-source-auth-runtime-upgrade.json`. It is a P9-owned one-target transition, not broker overwrite authority. Default mode is read-only preflight; `--apply` is separately LIVE-gated. The exact transition is only `4cb441873df8245387f06ee55d637a9f7b11cdc8 -> 130fc36a22bb4ace500b022c3defcccbf0893012` at the fixed existing `p9_source_auth.py` target.

The replacement is descriptor-safe and atomic: exact command-scoped Git `safe.directory`, safe root-owned parent chain, `O_NOFOLLOW` old-target validation, single-link regular-file requirement, fixed same-directory `O_EXCL` temporary creation, full write/metadata verification plus file `fsync`, duplicate old-target inode/blob check, same-directory `os.replace`, directory `fsync`, and exact post-replace verification. It deliberately has no in-place `ftruncate` rewrite and no automatic retry/rollback/cleanup after mutation starts. Source merge alone authorizes none of these runtime writes.

## Required continuation sequence

The current fail-closed sequence is:

1. complete the dedicated P9 Hermes source-auth runtime-upgrade source gate through focused branch -> Draft PR -> exact-head CI/review -> Ready, then require a separate explicit owner MERGE authorization;
2. after merge, freshly resolve exact `RPi5_main/main`, exact-main CI, upgrade-operator blob, installer blob and current Hermes helper provenance;
3. if needed, under a **new separate exact owner LIVE authorization**, converge only the reviewed trusted checkout to that merged main using the explicitly allowed `git fetch` + `git merge --ff-only` path; reset/rebase/stash/clean/force remain forbidden;
4. run the new P9 runtime-upgrade operator once in default read-only preflight mode without `--apply`; it must prove exact old blob `4cb441873df8245387f06ee55d637a9f7b11cdc8`, exact root ownership/mode, single-link regular-file identity, safe parent chain and absent fixed temp path;
5. only if that upgrade preflight passes may a separate explicit owner LIVE authorization replace exactly that one P9-owned target with reviewed blob `130fc36a22bb4ace500b022c3defcccbf0893012`;
6. after successful one-target convergence and fresh post-state proof, run a new fresh **default-mode read-only broker installer preflight** without `--apply`; the previous failed broker preflight is not retry authority;
7. only if that fresh broker preflight passes may a later separate owner LIVE authorization consider broker first-install `--apply` for exactly nine broker file materializations plus `systemctl daemon-reload` and socket `enable --now`; the shared P9 prerequisite remains outside broker mutation authority;
8. genuine audit dispatch, privileged dispatch enablement, runner retirement and later Phase/P11 work remain separately gated; any new failure after a live mutation starts requires evidence + STOP with no retry/rollback/cleanup/alternate path unless separately authorized.

Historical credential-placement, checkout, installer, failed-preflight and P10 authorizations are consumed, superseded or otherwise non-reusable and must not be reused as authority for this sequence.

## Safety state

`INSTALLER_SOURCE_IMPLEMENTED=true`  
`SOURCE_CREDENTIAL_PROVISIONER_IMPLEMENTED=true`
`SOURCE_CREDENTIAL_FIRST_INSTALL_RECEIPT=true`
`SOURCE_READ_AUTHORITY_PROVEN=false`  
`SOURCE_RUNTIME_CREDENTIAL_CURRENT_STATE_PROVEN=false`
`BROKER_ENTRYPOINT_WIRED=false`  
`HELPER_PROCESS_LAUNCH_WIRED=false`  
`PRIVILEGED_DISPATCH_ENABLED=false`  
`HOST_WIRING_ENABLED=false`  
`LIVE_INSTALL_ELIGIBLE=false`  
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`  
`RUNNER_RETIREMENT_ELIGIBLE=false`  
`PRODUCTION_MUTATION_STARTED=false`

This document and its manifests prove source provenance only. They do not prove actual RPi5 services, files, permissions, credentials, App installation scope, replay storage, broker socket/service state, helper installation, deployed SHA, or production data.

## Post-first-install local runtime-preflight source binding

The separately authorized P9 source-auth convergence and broker first-install are now accepted historical #191 evidence, but they do not alter this document's source-vs-runtime boundary. The installed broker is intentionally inert and no source file may infer current credential/App scope or end-to-end dispatch readiness from installation receipts alone.

The new local runtime prerequisite preflight is source-bound by `ops/deploy/hermes-deals-origin-runtime-prerequisite-preflight.json`. It may read only reviewed non-secret runtime code/registration/replay structures and credential metadata; it does not open the Source App private key and makes no GitHub API request. Consequently its maximum successful classification is `HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY`, with Source App installation scope and production replay/host-observation adapters explicitly unproven. Broker-entrypoint wiring, privileged dispatch, helper execution and genuine audit authorization remain false and separately gated.

## Current provenance binding — loopback-corrected helper (2026-09-06)

Canonical #191 continuity now supersedes the old helper as the current static identity without rewriting its historical first-install provenance. The accepted canary using `ops-workflows#35` / `deploy-authorizations#12` consumed replay and reached helper execution, then failed closed because the old helper targeted its historical fixed private-LAN origin; bounded evidence showed `http://127.0.0.1:9128` healthy. That authorization is consumed and is not retry authority.

Current reviewed Hermes source is exact `f6c48cc85c187d927575da6efef4b05b4d4c0e40` from #847/#848. Its helper identity is Git blob `4ef95c3f02b810b6b25721aa1b1b53d43b8ca572`, SHA-256 `23b29ff5f800cc5ade9cc8e38607a4e37beae9f45c6c82111ea4b49f063e06cf`; the probe remains blob `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`, SHA-256 `96a8b5819ec85f27095c535f1a3be6cba7bac0e2a40a1132869fb39dc669ad43`. The corresponding canonical registration is blob `a0444a84cb1a54abfeaefb47baf7f0c41b9677d8`, SHA-256 `36c511a36e462bf196a6695c4bac39497c56ab9ef7749aa0b2eb4621e172cad7`, size 338.

`ops/deploy/hermes-deals-origin-loopback-provenance-runtime-upgrade.json` binds the capability-specific transition from the historical installed identities to the corrected source. Its default operator mode is read-only preflight. Any future `--apply` is a separate owner LIVE gate and is limited to the three exact installed RPi5 consumer-binding modules plus helper plus registration; the probe is immutable. Source merge, checkout convergence, and this document do not authorize those runtime writes, a socket request, replay consume, helper execution, genuine audit, deployment, credential/systemd/Docker/network mutation, or runner retirement.
