# Hermes Deals Netto non-root preflight v2 — RPi5 source binding

Status: **SOURCE BINDING MERGED / FIRST-INSTALL CONTRACT DEFINED / EXECUTION DISABLED / LIVE NOT AUTHORIZED**

Tracking:

- merged RPi5 source binding: `RPi5_main#407` / PR #411 at `cb5a7b4098a3f85eff42d9e93202c1fda2bab716`;
- post-merge reconciliation: `RPi5_main#412` / PR #413;
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
- helper SHA-256: `275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c`;
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

## First-install source boundary

`ops/deploy/hermes-deals-netto-nonroot-preflight-v2-installer.json` and
`scripts/install-hermes-deals-netto-nonroot-preflight-v2.py` define a separate first-install-only
surface. The default installer mode is read-only preflight; root apply is not implied by this
source binding.

The installer binds the same frozen Hermes SHA, helper Git blob and helper SHA-256. It owns only
one fixed capability directory, the exact helper file (`root:root 0555`) and the canonical
registration (`root:root 0444`). Existing owned targets fail closed and are never adopted or
reconciled. The complete future apply budget is one directory plus two files.

The installer does not create its fixed Hermes trusted checkout. Checkout preparation, installer
apply, post-install verification, execution-identity wiring and genuine canary invocation remain
separate gates. See `docs/HERMES_DEALS_NETTO_NONROOT_PREFLIGHT_V2_INSTALLATION.md`.

## Trust boundary

The reviewed helper is intentionally non-root and rejects Docker-group authority. Its bounded evidence can expose only sanitized readiness/permission metadata plus fixed false mutation flags. It does not export N9 or corpus file contents and it does not run the parser.

Neither the source binding nor the first installer grants:

- arbitrary command/path/argv/environment authority;
- helper/canary execution;
- root/sudo authority outside the separately owner-gated exact installer apply;
- Docker authority or user/group mutation;
- parser execution;
- production database writes;
- Review/publication writes;
- deployment/cutover;
- systemd/service mutation;
- runner registration/deregistration;
- GitHub App, credential or permission mutation;
- automatic retry, cleanup or rollback.

## Gate separation

Source proves only reviewed intent and immutable provenance; it never proves current RPi5
installation, ownership, permissions, corpus accessibility, runner state or runtime health.

The next installation sequence is:

1. freshly verify merged RPi5 source and exact-main CI;
2. fresh trusted-host read-only installation preflight;
3. if required, separately authorize creation of the fixed detached Hermes trusted checkout;
4. separately authorize the exact root first-install `--apply` budget;
5. freshly verify installed targets read-only;
6. make a separate source decision for a compliant non-root/no-Docker execution identity;
7. authorize any genuine read-only Netto canary only in a later independent READY/LIVE-AUTH envelope.

Runner retirement remains ineligible until all required Hermes capability classes have accepted
runner-independent replacements.

Merge never authorizes LIVE work. Installation never authorizes invocation.
