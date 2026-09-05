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

`installer_source_blob=6762f6dffa7908cc8e8dd8fb7c144c1433edbe54`

The installer is deliberately narrower than generic privileged shell access:

- default invocation is read-only preflight; `--apply` requires root and a separate explicit LIVE owner authorization;
- it requires an exact checkout SHA supplied by the operator, proves that SHA is descendant-or-equal to the immutable implementation baseline, verifies its own tracked source at that SHA, and verifies all ten frozen install-target Git blobs;
- root-side Git provenance uses only command-scoped `safe.directory=<exact resolved REPO_ROOT>` while preserving the fixed minimal subprocess environment; wildcard trust and root global/system Git config mutation are forbidden;
- it checks only allowlisted runtime metadata: trusted root-owned parent directories, the fixed `rozkalns-deploy-executor` group, and source GitHub App credential **path/owner/group/mode only**;
- it never reads credential contents and never creates, replaces, chmods or otherwise mutates credentials;
- it is first-install-only: any pre-existing install target fails closed before mutation and requires a separate reconciliation source gate;
- its apply surface is exactly ten reviewed file materializations followed by `systemctl daemon-reload` and `systemctl enable --now rozkalns-hermes-deals-origin-broker.socket`;
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

## Required continuation sequence

The current fail-closed sequence is:

1. merge the reviewed #383 broker-installer root Git trust repair only after exact-head CI/review convergence and explicit owner MERGE authorization;
2. refresh exact `RPi5_main/main`, exact-main CI and the installer source blob;
3. run a **fresh default-mode read-only broker installer preflight** under owner-controlled root execution on that exact current main, without `--apply`;
4. only if that preflight passes may a later separate owner LIVE authorization consider broker installer `--apply`;
5. broker installation/systemd socket activation, genuine audit dispatch and runner retirement remain separately gated;
6. any new preflight failure remains fail-closed and must be analyzed before any retry.

A previous preflight failure must not be rerun as a substitute for this sequence, and no historical authorization may be reused.

## Safety state

`INSTALLER_SOURCE_IMPLEMENTED=true`  
`SOURCE_CREDENTIAL_PROVISIONER_IMPLEMENTED=true`
`SOURCE_READ_AUTHORITY_PROVEN=false`  
`SOURCE_RUNTIME_CREDENTIAL_PROVEN=false`
`BROKER_ENTRYPOINT_WIRED=false`  
`HELPER_PROCESS_LAUNCH_WIRED=false`  
`PRIVILEGED_DISPATCH_ENABLED=false`  
`HOST_WIRING_ENABLED=false`  
`LIVE_INSTALL_ELIGIBLE=false`  
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`  
`RUNNER_RETIREMENT_ELIGIBLE=false`  
`PRODUCTION_MUTATION_STARTED=false`

This document and its manifests prove source provenance only. They do not prove actual RPi5 services, files, permissions, credentials, App installation scope, replay storage, broker socket/service state, helper installation, deployed SHA, or production data.
