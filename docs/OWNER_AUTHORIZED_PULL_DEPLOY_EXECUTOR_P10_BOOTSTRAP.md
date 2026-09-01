# Owner-authorized pull deploy executor v1 — P10 hardened controller bootstrap

Status: SOURCE IMPLEMENTED / EXECUTION DISABLED
Roadmap: `RPi5_main#236`
Queue: `ops-workflows#28`
Dashboard candidate: `5f7739348f56398d0ba301c9320e1de0062838fc`
Machine contract: `ops/deploy/p10-dashboard-bootstrap.json`
Source operation: `dashboard-rpi5.hardened-controller-bootstrap.v1`

## Why this gate exists

The repaired P10 trusted-host preflight successfully built the exact Dashboard ARM64 candidate, explicitly built and staged `node-pty`, verified the production candidate manifest and passed isolated production runtime smoke. It then stopped before `sudo` and before any privileged PLAN because the controller reached through `/opt/dashboard_RPi5/current` had Git blob:

`c501bea57c0d5c35e7961ae1f1e5593a02268661`

That blob is known GitHub source from Dashboard commit `400296591ec14c062e4c3c9fdbc95c38109ba0fd`, which added the historical root-only read-only PLAN path. It is not evidence of arbitrary host tampering.

However, it predates the descriptor-safe/current-release trust boundary introduced later by Dashboard issue `#236` / hardening commit `da49cfa0940fd7897f53674c72b4f9b54e4f239b`. Dashboard's canonical `docs/PHASE11D_RELEASE_ACTIVATION.md` explicitly requires a separate first hardened-controller bootstrap when the current verified release predates that boundary.

## Security decision

`c501bea57c0d5c35e7961ae1f1e5593a02268661` is classified as **known historical, bootstrap required**.

It must not be treated as a third normal P10 PLAN allowlist identity. In particular:

- do not execute operator-writable candidate JavaScript as root;
- do not patch the current immutable release in place;
- do not copy/replace only the installed controller as a preflight workaround;
- do not retry the consumed preflight authorization;
- do not use an alternate controller path merely to make PLAN pass.

The normal hardened controller identities remain:

- `7fcc58cbea2f1247d6e4d93bc3805923697fbfab` — reviewed hardened legacy controller;
- `c0566adb76e044632a4556dbefeb0f46839b4996` — current symlink-safe hardened controller.

## What the successful preflight already proves

The latest trusted-host attempt established, for exact Dashboard `5f7739348f56398d0ba301c9320e1de0062838fc`:

- Node 24 / Linux ARM64 build prerequisites were sufficient;
- `npm ci --ignore-scripts` completed;
- explicit `node-pty` source rebuild completed;
- native runtime staging returned `NATIVE_RUNTIME_PACKAGED=YES`;
- candidate manifest generation completed;
- manifest verification returned `MANIFEST_VERIFIED=YES`;
- isolated production runtime smoke returned `RUNTIME_SMOKE=PASS`;
- controller classification stopped before privileged invocation;
- privileged PLAN attempts = 0;
- production mutation started = NO;
- P10 APPLY executed = NO;
- retry allowed = NO.

This evidence narrows the remaining P10 blocker to the first hardened-controller bootstrap trust anchor; it does not authorize any host mutation.

## Implemented source capability

The dedicated source implementation is intentionally outside the normal executor operation registry. `ops/deploy/executor-operations.json` remains globally `execution_enabled=false`, preserving the existing P9 exact-registry contract. The bootstrap is a one-time prerequisite, not an ordinary deploy operation and not a permanent alternate channel.

Reviewed source surfaces:

- source/dormant adapter API: `ops/lib/deploy_executor/dashboard_bootstrap_contract.py`;
- dormant adapter implementation: `ops/lib/deploy_executor/dashboard_bootstrap_adapter.py`;
- descriptor-safe filesystem implementation: `ops/lib/deploy_executor/dashboard_bootstrap_fs.py`;
- one-shot bootstrap orchestrator: `ops/lib/deploy_executor/dashboard_bootstrap.py`;
- narrow source wrapper: `ops/bin/rozkalns-dashboard-controller-bootstrap`;
- machine contract: `ops/deploy/p10-dashboard-bootstrap.json`;
- regression: `tests/test-deploy-executor-p10-bootstrap-adapter.py` and `tests/test-deploy-executor-p10-bootstrap.py`.

The future installed identities are fixed to:

- helper: `/usr/local/sbin/rozkalns-dashboard-controller-bootstrap`;
- library root: `/usr/local/lib/rozkalns-deploy-executor`;
- live bootstrap package root: `/usr/local/lib/rozkalns-deploy-executor/deploy_executor`.

This source PR does **not** install any of these paths.

### Privileged trust anchor before import

The helper itself is a separately reviewed trust anchor. Before a future LIVE invocation, the host preflight must verify the installed helper at the fixed path against the exact source-wrapper Git blob recorded in `ops/deploy/p10-dashboard-bootstrap.json`. Runtime then requires that fixed helper path to be a real `root:root 0755` file, checks `/usr`, `/usr/local`, `/usr/local/lib` and `/usr/local/sbin` are root-owned and not group/world writable, and requires `/usr/local/lib/rozkalns-deploy-executor` itself to be a real `root:root 0755` directory.

Critically, **before any installed bootstrap Python module is imported**, the wrapper descriptor-safely opens the fixed package root and requires it to be `root:root 0755`. It then opens exactly these live modules with `O_NOFOLLOW`, requires `root:root 0644`, applies a bounded size check and verifies their exact reviewed Git blobs from the machine contract:

- `dashboard_bootstrap_contract.py`;
- `dashboard_bootstrap_fs.py`;
- `dashboard_bootstrap.py`.

The dormant adapter is deliberately outside that privileged import closure. The wrapper creates a private synthetic package rooted only at the already verified directory, disables bytecode writes and imports only those three exact modules. Normal `deploy_executor/__init__.py` is not executed, so its broader protocol/state/transport imports do not become bootstrap root authority.

This closes the previously possible gap where a root helper could have imported mutable installed library code before proving its provenance. The wrapper does not self-hash recursively; its exact blob is instead a required external pre-invocation LIVE/preflight identity, while runtime independently verifies its fixed path and metadata.

### Fixed inputs only

The helper has no candidate-root, manifest-path, production-root, command, script or arbitrary argv option. The only runtime values it accepts are:

```text
--expected-current <40-lowercase-hex>
--expected-candidate <64-lowercase-hex>
--apply
--ack I_AUTHORIZED_DASHBOARD_RPI5_HARDENED_CONTROLLER_BOOTSTRAP
```

Candidate and manifest locations are source constants bound to exact Dashboard `5f7739348f56398d0ba301c9320e1de0062838fc`:

```text
/var/lib/rozkalns-deploy-executor/bootstrap/dashboard-rpi5/5f7739348f56398d0ba301c9320e1de0062838fc/source
/var/lib/rozkalns-deploy-executor/bootstrap/dashboard-rpi5/5f7739348f56398d0ba301c9320e1de0062838fc/candidate-manifest.json
```

The production root is fixed to `/opt/dashboard_RPi5`.

### Descriptor-safe candidate consumption

The helper does not execute candidate JavaScript and does not delegate copying to a subprocess. It requires Linux `/proc/self/fd`, opens directory components with `O_DIRECTORY | O_NOFOLLOW`, opens final files with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK`, and validates the same open descriptor used for hashing/copying.

The candidate manifest is strict bounded UTF-8 JSON with duplicate-key rejection. It is bound to the exact source SHA and the `candidateSha256` already reviewed by preflight. Manifest file paths are relative, sorted, duplicate-free and bounded; symlinks, `..`, reserved marker paths and `node_modules` are rejected.

The candidate `tools/production-release-controller.mjs` bytes must have exact Git blob:

`c0566adb76e044632a4556dbefeb0f46839b4996`

The historical installed release uses the same `dashboard-rpi5.production-candidate.v1` marker schema at commit `400296591ec14c062e4c3c9fdbc95c38109ba0fd`; its marker is verified against its own exact current SHA rather than incorrectly assuming the new candidate SHA.

### Historical trust-root prerequisite

Before the apply lock is created, and again while holding it, the helper requires:

- root execution through the reviewed installed helper boundary;
- production root and `releases` root as real reviewed directories;
- `current` exactly `releases/<expected-current>`;
- the entire historical current release to match its root-owned installed candidate manifest;
- historical current controller Git blob exactly `c501bea57c0d5c35e7961ae1f1e5593a02268661`;
- exact target release `releases/5f773934...` to be absent.

If the hardened candidate is already current, bootstrap fails before mutation and the normal P10 controller path must be used. Existing target-release evidence also fails closed; the helper does not turn into a retry or cleanup path.

## Exact mutation budget

One separately LIVE/root-authorized bootstrap may perform at most:

1. one exclusive `.dashboard-release-controller.lock` lifecycle;
2. one exact `releases/5f7739348f56398d0ba301c9320e1de0062838fc` materialization;
3. one atomic `current` pointer swap to that exact release.

Internal bounds are also fixed:

- candidate manifest maximum: 4 MiB;
- maximum manifest files: 512;
- maximum aggregate manifest bytes: 512 MiB;
- destination files are created exclusive and private `0600`, then changed to reviewed root-owned `0644` only after exact source descriptor size/hash copy succeeds;
- release directories are root-owned `0755`;
- installed marker is root-owned `0600`;
- previous releases deleted: 0;
- rollback attempts: 0;
- P10 application APPLY operations: 0.

The helper performs no package, systemd, service, Docker, network, Cloudflare, credential, DB or identity mutation and starts no child process.

## Fail-closed mutation evidence

The apply lock is transient only while no release mutation has started.

```text
PRE-RELEASE-MUTATION FAILURE
  -> close descriptors
  -> remove only the transient bootstrap/apply lock
  -> no retry implied

POST-RELEASE-MUTATION FAILURE
  -> preserve apply lock
  -> preserve partial exact release/current-pointer evidence
  -> STOP
  -> no retry, cleanup, alternate path or automatic rollback

SUCCESS
  -> verify exact new installed release + hardened controller + current pointer
  -> remove transient lock
  -> P10 application APPLY remains false
```

After success, the historical release is retained and the helper no longer qualifies as a useful deploy channel: a subsequent call against candidate-as-current fails before mutation. Ordinary P10 must return to `/opt/dashboard_RPi5/current/tools/production-release-controller.mjs`.

## Source/live separation

This implementation remains **execution-disabled** source. Source merge does not authorize:

- installing the helper/library;
- creating the fixed staging tree;
- placing candidate/manifest bytes on the host;
- host filesystem mutation;
- `sudo` or root execution;
- current symlink mutation;
- production PLAN retry;
- production APPLY/deploy;
- service/systemd/Docker/Cloudflare mutation;
- permissions/identity/credential changes;
- cleanup of preserved evidence.

After source merge and exact-main CI, the next step is read-only revalidation of source/helper identities, Dashboard exact candidate/CI, #28 and the current host baseline. Only then may the owner issue a **separate exact LIVE bootstrap authorization**. Bootstrap success must STOP for fresh ordinary P10 PLAN reconciliation; it must not continue directly into P10 APPLY.

## Queue state

`ops-workflows#28` remains WAITING. While this implementation is unmerged, its reason is `WAITING_HARDENED_CONTROLLER_BOOTSTRAP_SOURCE_MERGE`.

After merge, exact-main CI and source identity revalidation, #28 still remains WAITING behind the separate LIVE/root bootstrap gate. It must not become READY until the bootstrap succeeds, post-bootstrap state is revalidated, and a fresh ordinary P10 PLAN produces the reviewed application baseline.
