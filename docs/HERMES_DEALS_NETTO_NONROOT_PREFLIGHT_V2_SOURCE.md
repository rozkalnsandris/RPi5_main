# Hermes Deals Netto non-root preflight v2 — RPi5 source binding

Status: **SOURCE BINDING MERGED / EXECUTION DISABLED / LIVE NOT AUTHORIZED**

Tracking:

- current post-merge continuity work item: `RPi5_main#412`;
- merged RPi5 source binding: `RPi5_main#407` / PR #411 at `cb5a7b4098a3f85eff42d9e93202c1fda2bab716`;
- upstream helper source: `hermes-deals#858` / PR #859;
- Phase 4 umbrella continuity: `RPi5_main#191`;
- residual runner migration: `hermes-deals#384`.

## Reviewed upstream source

The RPi5 binding is frozen to the merged Hermes source:

- repository: `rozkalnsandris/hermes-deals`;
- stable repository ID: `1317143994`;
- merged source SHA: `067db7bd4b8057bc16a9bf0ef9ed8487127a0a05`;
- helper source path: `tools/runner/netto_missing_normal_price_nonroot_preflight_v2.py`;
- helper Git blob: `0f8b01ed3129323cc59e526262b369cf33346aba`;
- exact-main Hermes CI #1819: `SUCCESS`;
- GITHUB-ONLY policy drift #136: `SUCCESS`.

The helper source fixes capability `netto-missing-normal-price-nonroot-preflight-v2`, registration schema `rozkalns.hermes-deals.netto-nonroot-preflight-v2-registration.v1`, evidence schema `rozkalns.hermes-deals.netto-nonroot-preflight-v2-evidence.v1`, and exactly one caller-visible argument: `registered_source_sha`.

The helper also source-fixes its registration/install targets, N9 manifest identity and corpus root. The registry does not copy those filesystem paths into caller authority. Their semantics are inherited only through the immutable reviewed helper blob and the explicit N9 manifest SHA-256 `2b180d67af4c5d1e586704088e3d685cff21ae2e12f3052254daf4553dd4e147`.

## Static RPi5 operation

`ops/deploy/executor-operations.json` registers exactly one capability-specific operation:

- operation / adapter: `hermes-deals.netto-missing-normal-price-nonroot-preflight-v2.v1`;
- target alias: `hermes-deals-netto-nonroot-preflight-v2`;
- authorization class: `STRICT`;
- ordinary LIVE-ALL eligible: `false`;
- rollback: `NONE`;
- maximum future invocation budget: one read-only Netto v2 preflight invocation;
- baseline resolver contract: `hermes-deals.netto-nonroot-preflight-v2-registration.v1`;
- production registry remains globally `execution_enabled=false`.

`HermesDealsNettoNonrootPreflightV2Adapter` accepts only the exact reviewed Hermes SHA and fixed helper provenance/interface. `apply()` always fails closed. The adapter contains no process-launch, shell, socket, sudo, Docker or generic command/path/argv/environment bridge.

## Trust boundary

The reviewed helper is intentionally non-root and rejects Docker-group authority. Its bounded evidence can expose only sanitized readiness/permission metadata plus fixed false mutation flags. It does not export N9 or corpus file contents and it does not run the parser.

This source binding explicitly excludes:

- root/sudo or Docker authority;
- parser execution;
- production database writes;
- Review/publication writes;
- deployment/cutover;
- systemd/service/host mutation;
- runner registration/deregistration;
- GitHub App, credential or permission mutation;
- arbitrary command/path/argv/environment authority;
- automatic retry, cleanup or rollback.

## Gate separation

The merged source binding proves source compatibility only. It does **not** prove current RPi5 installation, registration, ownership, permissions, corpus accessibility, runner state or runtime health.

The exact next gate is fresh trusted-host read-only evidence. After that evidence is reviewed, any helper installation or host wiring still requires its own explicit LIVE authorization. A genuine read-only Netto canary requires a later independent READY/LIVE-AUTH envelope. Runner retirement remains ineligible until all required Hermes capability classes have accepted runner-independent replacements.

Merge never authorizes LIVE work.
