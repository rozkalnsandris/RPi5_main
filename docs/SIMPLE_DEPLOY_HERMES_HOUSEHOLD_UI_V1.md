# Hermes household UI configuration — #973

Status: **SOURCE CONFIGURATION ONLY / NOT LIVE READY**.

Hermes consumer source `4467939c8c26378ee6d8dc3029fba2e562c5e48c` includes the
Jinja/HTMX household UI and server-validated forms. The application's Compose
forwarding does not propagate into the RPi5-owned API-only adapter. This source
change closes that configuration gap without changing the protected env projection.

## Selected source model

The current source registry selects `hermes-deals-household-api.yml` for the same
`hermes-deals` project and `api` service. Its bytes differ from the legacy adapter
only by two fixed environment values:

| Setting | Value | Basis |
| --- | --- | --- |
| `HERMES_HOUSEHOLD_ID` | `home` | Existing consumer default; preserves the default shared list identity. |
| `HERMES_PUBLIC_ORIGIN` | `https://deals.rozkalns.net` | Tracked private ingress hostname; server validates browser form origin against this value. |

These are public configuration, not credentials. They belong in the reviewed
static adapter, not the protected env file. There is no caller/process environment
interpolation. Compose's explicit environment values take precedence over any
same-named env-file values, so an existing non-default household identity or origin
must stop adoption until separately reviewed; never silently switch a family's list.
The hostname is source intent, not a fresh observation of live access or routing.

The source contract `ops/contracts/simple-deploy-hermes-household-ui-v1.json`,
current target registry and host contract bind the same adapter SHA-256. The private
file contract remains exactly `DATABASE_URL` and `HTTP_USER_AGENT`. API dependency
isolation, image, network, mounts, health check and generic executor are unchanged.

## Installation and legacy boundaries

Source registry selection is not host installation. The installed registry and
Compose file are not automatically replaced by this PR. A registry-only update
would refer to a missing adapter and must fail closed. Publish matching reviewed
registry/adapter bytes together only under a later bounded adoption outcome.

The original `hermes-deals-api.yml`, frozen Weather/Hermes baseline and v1 adoption
script/contract remain unchanged. V1 adoption still installs the legacy model and
is not an installation path for this successor. The generic first-install script
also does not install this new adapter and must not be used as an upgrade shortcut.
No adoption/apply entrypoint is added here.

Weather rebind also pins the shared registry as a whole. Its source contract now
reads the frozen pre-household registry from
`ops/deploy/baselines/simple-deploy-targets-weather-rebind-v1.json`; its approved
digest and Weather-only delta are unchanged. Advancing the current Hermes registry
must not silently broaden the separate Weather operation.

## Remaining prerequisites

1. Revalidate exact consumer release/digest, source target and runtime baseline.
2. Resolve [v4 consumer access](SIMPLE_DEPLOY_HERMES_PREREQUISITE_MATERIALIZATION_V4.md):
   its metadata-only result cannot prove Compose can read the protected child.
   V4 has no apply path; v2/v3 are not fallback installers for its parent layout.
3. Review an existing-install adoption outcome for this adapter/registry together
   with a valid protected prerequisite path. Preserve unrelated targets and validate
   any existing household identity/origin without printing protected values.
4. Prove DB backup/restore and the bounded household-state schema prerequisite;
   ordinary API image reconciliation does not migrate the database.
5. Prepare the Nginx `/ui/home/` route and verify exact-release access, forms,
   CSRF/origin, concurrent household version checks, mobile/keyboard and assets.

See the consumer [rollout plan at the reviewed source](https://github.com/rozkalnsandris/hermes-deals/blob/4467939c8c26378ee6d8dc3029fba2e562c5e48c/docs/plan/ROLLOUT_PREFLIGHT.md).
Its v3 discussion is supplemented by the v4 access boundary above. Hermes activation
remains fleet-last; source readiness does not select a LIVE target or restore timers.

## Verification

`python3 tests/test-simple-deploy-hermes-household-ui-v1.py` verifies the exact
additive adapter delta, source registry/hash wiring, ingress identity, unchanged
private projection contract and preserved legacy adoption baseline. The existing
compatibility, generic reconciler, installer, adoption and v1-v4 prerequisite suites
remain applicable. Tests use repository source and synthetic fixtures only; they
never open the protected host file or run Docker/Compose against it.

Production deploy/change REQUIRED: NO. Merge does not authorize protected reads,
materialization, permissions, DB writes, host configuration or runtime activation.
