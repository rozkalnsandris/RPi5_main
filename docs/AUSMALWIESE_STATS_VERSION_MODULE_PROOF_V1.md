# Ausmalwiese Stats Worker — pinned Wrangler provenance workflow (#1050)

**SOURCE ONLY / NO MERGE / NO LIVE.**

The earlier #1045 simplification remains the deployment model: Cloudflare Workers
separates versions from deployments, so the future flow uploads one version,
captures its exact full Version ID, and deploys only that ID at 100% traffic.
Issue #1050 closes the remaining reproducibility gap by pinning both the Wrangler
version and the exact merged application config provenance.

## Frozen source provenance

- Application repository: `rozkalnsandris/coloring-pages`
- Application commit: `180368f3b81abddde3df94637512436ca50c358f`
- Worker source: `cloudflare/stats-worker.js`
- Worker Git blob SHA-1: `dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4`
- Wrangler config: `cloudflare/wrangler.stats-worker.jsonc`
- Wrangler config Git blob SHA-1:
  `3733263a391274f2b6b0f2023c8656565bde8e1a`
- Wrangler version: `4.135.0`
- Worker: `coloring-pages-stats-v1`

The source-only planner rejects any different application commit, Worker bytes,
config bytes or Wrangler version before producing a future command array.

## Exact reviewed config semantics

The pinned config is deliberately narrow:

- `compatibility_date = 2026-10-06`
- `workers_dev = false`
- `keep_vars = true`
- D1 `DB` -> `coloring-pages-stats-v1`,
  `f8ac8f1d-a230-4bc4-af13-557c1b91b273`
- `RATE_LIMITER` namespace `1152026106`, policy `100 / 60s`
- required secret names only:
  `CF_ANALYTICS_API_TOKEN`, `VISITOR_HMAC_KEY`
- no routes, triggers, compatibility flags, plaintext vars, account ID or zone ID

Secret values are not read or stored. Existing plaintext variables remain remote
state and are preserved by `keep_vars=true`.

## Future command shape

The planner emits an exact Wrangler package version instead of an unpinned
`npx wrangler`:

    npx --yes wrangler@4.135.0 versions upload cloudflare/stats-worker.js \
      --config cloudflare/wrangler.stats-worker.jsonc \
      --name coloring-pages-stats-v1 \
      --no-bundle --keep-vars --strict \
      --tag git:180368f3b81abddde3df94637512436ca50c358f \
      --message source-blob:dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4,config-blob:3733263a391274f2b6b0f2023c8656565bde8e1a

Then, only after capturing the exact returned full UUID:

    npx --yes wrangler@4.135.0 versions deploy <VERSION-ID>@100% \
      --config cloudflare/wrangler.stats-worker.jsonc \
      --name coloring-pages-stats-v1 -y

Finally, the read-only behavior check remains:

    curl --fail-with-body --silent --show-error --head https://ausmalwiese.de/q

No route command, secret mutation, D1 data/schema mutation or rollback is part of
this workflow.

## Runtime boundary

The RPi5 read-only preflight on 2026-10-17 observed Wrangler `4.135.0`, Node
`v24.21.0` and npm `12.0.1`. That observation is evidence only; this source
issue does not run Wrangler or install packages.

Using `npx --yes wrangler@4.135.0` in a future LIVE operation can populate npm
runtime/cache state and contact the package registry. That future execution is
not authorized here. A separate LIVE authorization must explicitly bind the
final merged RPi5_main SHA, the exact application commit/config blob above,
Wrangler `4.135.0`, target Worker and the bounded upload/deploy sequence.

## Remaining gates

- Exact-head CI/review for this source-only change.
- Explicit merge authority is still required because issue #1050 itself freezes
  `NO MERGE`, even when driven through AUTO-RUN FULL.
- Actual Wrangler/package execution, credentials and Cloudflare upload/deploy
  require a separate LIVE authorization.
- If upload/deploy outcome is uncertain, STOP. No automatic retry, rollback or
  cleanup.

Cloudflare references:

- https://developers.cloudflare.com/workers/versions-and-deployments/
- https://developers.cloudflare.com/workers/versions-and-deployments/deployment-management/
- https://developers.cloudflare.com/workers/wrangler/commands/workers/
- https://developers.cloudflare.com/workers/wrangler/configuration/
