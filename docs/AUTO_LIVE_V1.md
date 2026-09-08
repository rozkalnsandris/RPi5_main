# AUTO-LIVE v1

Status: **A0 SOURCE CONTRACT ONLY**
Roadmap: `RPi5_main#421`
Machine contract: `ops/deploy/auto-live-v1.json`

## Purpose

Auto-Live v1 replaces the normal operator loop `GITHUB-ONLY -> deferred LIVE-ALL` with automatic post-merge reconciliation for production-bearing repositories. It does **not** make every merge an unrestricted production authorization.

Target steady state:

```text
reviewed PR
  -> merge
  -> trusted RPi5 observes current main
  -> exact merged SHA + exact-SHA CI
  -> full production-baseline -> target classification
  -> static project capability
  -> AUTO_DEPLOY_SAFE: automatic bounded apply
     NO_DEPLOY: reconcile only
     sensitive/unknown: owner-required / fail closed
  -> health + immutable/public-safe evidence
```

## Trigger is not authority

A merge is the event that creates a new source candidate. Persistent authority for an ordinary automatic deployment comes only from a separately reviewed and activated repository Auto-Live manifest plus a static RPi5 operation contract.

This distinction prevents a repository edit from silently inventing a new root, credential, database, networking or control-plane permission. First activation of the host-side Auto-Live capability remains a separate owner LIVE gate.

## Steady-state detection

The canonical detector is an outbound trusted RPi5 poller/controller. The current deployment plane already uses a persistent two-minute polling pattern, so Auto-Live should extend/reuse that architecture instead of exposing a new inbound RPi5 endpoint.

GitHub documents `push` to `main` as a normal deployment trigger and `concurrency` as the mechanism for serializing deployments. Auto-Live may later use a GitHub-side `push` workflow as an auxiliary signal/status surface, but GitHub-side event delivery is not required for correctness of the RPi5 controller.

## Remote Desktop Commander boundary

Remote Desktop Commander is the owner-controlled bootstrap, installation, convergence, verification and recovery channel. It is **not** the production merge detector, authorization database or generic privileged execution plane.

The upstream security model states that tool calls execute with the paired user's permissions and that a machine is reachable only while the device agent is running. Those properties are useful for owner-controlled maintenance, but they are intentionally not a durable production trigger contract.

## Existing primitives to reuse

Auto-Live must compose existing reviewed primitives rather than create a second generic deploy transport:

- `AUTO-RUN FULL v2` for issue/source/PR/merge orchestration;
- `RPi5_main#236` pull-deploy executor protocol and replay/fail-closed concepts;
- `ops/deploy/executor-operations.json` static capability registry;
- the trusted RPi5 polling/timer model;
- the proven CV full-range deploy-impact classifier and controller pattern;
- per-project fixed adapters/helpers, target baselines, health checks and rollback semantics.

## Deployment classes

### `NO_DEPLOY`

The new SHA is recorded/reconciled. No production mutation occurs.

### `AUTO_DEPLOY_SAFE`

Automatic mutation is allowed only after that repository/target has completed its Auto-Live activation canary and every current gate passes. Required gates include exact merged SHA, exact-SHA CI, full baseline-to-target classification, active manifest, static eligible operation, exact target/baseline, installed adapter/helper identity, per-target serialization and deterministic health/postconditions.

### `MANUAL_ROLLOUT_REQUIRED` and `DB_HOST_APPLY_REQUIRED`

These remain owner-required by default. A later source policy may narrow one specific operation class into automatic eligibility only after an explicit review/canary/activation cycle.

### Unknown

Unknown runtime-relevant paths or incomplete evidence fail closed.

## Superseding merges

If several merges arrive before any production mutation starts, the controller may skip an older pending target and evaluate the newest current-main target, but only by reclassifying the **complete** production-baseline -> newest-target range.

Once mutation starts, a newer merge never changes the authority or target of that in-flight deployment.

## Concurrency

Each production target has one stable concurrency key. At most one mutation-capable deployment may run per target. Independent targets may continue independently.

## Failure semantics

Before mutation, only already-reviewed bounded read/transport retries are allowed. After the first production mutation begins, error, ambiguity or drift means public-safe evidence + STOP for that target. There is no automatic retry, cleanup, alternate path or rollback unless that exact transactional behavior was predeclared by the operation contract.

## Credentials

Use least-privilege GitHub App installation authentication. GitHub documents that installation access tokens can be narrowed to repositories/permissions and expire after one hour. Long-lived PAT classic and SSH command transport are not Auto-Live dependencies.

## `GITHUB-ONLY / LIVE-ALL` retirement

Current RPi5 routing already requires `GITHUB-ONLY` to be explicit; it is not the bare continuation default. A0 changes no command behavior.

A1-A5 will introduce the shared Auto-Live policy, migrate repository manifests/adapters, prove a real canary per capability and only then mark/remove the old normal `GITHUB-ONLY / LIVE-ALL` compatibility path. Historical queue/authorization evidence remains retained as audit history.

## Rollout

1. **A0** — this source contract, threat boundary and tests; runtime unchanged.
2. **A1** — shared `ops-workflows` Auto-Live policy; compatibility retained.
3. **A2** — opt-in per-repository manifests; no manifest means no auto mutation.
4. **A3** — read-only RPi5 controller decisions with mutation disabled.
5. **A4** — one genuine low-risk canary under a separate owner LIVE activation.
6. **A5** — one target at a time scale-out, then compatibility retirement.

## Threats explicitly rejected

- arbitrary command/path/argv/environment from GitHub content;
- merge as blanket root/DB/credential/network/control-plane authorization;
- public inbound RPi5 webhook/API;
- persistent public-repository self-hosted Actions deployment runner;
- PAT classic or generic SSH deployment transport;
- source documents treated as runtime proof;
- historical authorization replay;
- automatic mutation retry after ambiguity/failure.

## External references reviewed for A0

- GitHub Actions deployment triggers/environments/concurrency: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments
- GitHub App installation access tokens: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- Remote Desktop Commander registry/security model: https://github.com/mcp/app.desktopcommander/remote-desktop-commander
- Remote Desktop Commander security policy: https://github.com/desktop-commander/remote-desktop-commander/blob/main/SECURITY.md

## A0 safety boundary

A0 is source/docs/tests only. `execution_enabled=false`. It performs no host/runtime, systemd/timer, credential/App permission, database, Cloudflare or production deployment mutation.
