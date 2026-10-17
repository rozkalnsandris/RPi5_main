# Ausmalwiese Stats Worker — simplified Wrangler version workflow (#1045)

**SOURCE ONLY / NO MERGE / NO LIVE.**

The earlier plan to download a deployed Worker module and prove its SHA-256 again is intentionally dropped. Cloudflare Workers already separates **versions** from **deployments**: `wrangler versions upload` creates a version without sending production traffic to it, and `wrangler versions deploy <VERSION>@100%` promotes one exact version. A Worker version captures code, bindings and compatibility settings.

This source keeps only the controls that materially protect this deployment:

1. Git remains the source of truth for `coloring-pages@9590be4276ac1781eafe38cf662b8d224653c9aa:cloudflare/stats-worker.js`, blob `dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4`.
2. One reviewed `cloudflare/wrangler.stats-worker.jsonc` must be added to `coloring-pages` in a separate source change. Use `wrangler init --from-dash coloring-pages-stats-v1` once as a starting point, then review the generated configuration before committing it. Do not treat later Dashboard edits as canonical.
3. The config must name only `coloring-pages-stats-v1`, use `workers_dev=false`, `keep_vars=true`, contain the existing `DB` D1 binding and `RATE_LIMITER` binding, and declare required secrets `CF_ANALYTICS_API_TOKEN` and `VISITOR_HMAC_KEY`. Plain-text dashboard vars stay remote via `keep_vars=true`.
4. The config deliberately contains **no `route`, `routes` or triggers**. `wrangler versions upload` does not apply route/trigger changes; Cloudflare documents `wrangler triggers deploy` as the separate trigger operation.
5. Future upload uses `--no-bundle --keep-vars --strict`, with the Git commit as tag. `--no-bundle` avoids an unnecessary bundling transformation; `--strict` makes Wrangler stop on conflicting remote state.
6. Capture the full Version ID produced by upload and deploy only that UUID at `100%`. Never use `latest` as the deployment target.
7. Verify `HEAD https://ausmalwiese.de/q` returns the expected redirect. HEAD is used because the Worker implementation does not increment the QR scan counter for HEAD.

The source-only module in this PR only validates the config shape and produces the exact command arrays as data. It cannot execute Wrangler, read credentials, contact Cloudflare or deploy.

## Future command shape

Upload, after the reviewed config exists and a separately authorized runtime has credentials:

    npx wrangler versions upload cloudflare/stats-worker.js \
      --config cloudflare/wrangler.stats-worker.jsonc \
      --name coloring-pages-stats-v1 \
      --no-bundle --keep-vars --strict \
      --tag git:9590be4276ac1781eafe38cf662b8d224653c9aa \
      --message source-blob:dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4

Then deploy the exact returned UUID:

    npx wrangler versions deploy <VERSION-ID>@100% \
      --config cloudflare/wrangler.stats-worker.jsonc \
      --name coloring-pages-stats-v1 -y

No route command, secret mutation, D1 data mutation or rollback is part of this workflow.

## Remaining gates

- Merge this source only after exact-head CI/review and explicit owner MERGE.
- Add/review the Wrangler config in `coloring-pages`; that is a separate repository source change.
- Actual Wrangler authentication and Cloudflare upload/deploy remain separate LIVE authorization.
- If upload/deploy outcome is uncertain, STOP. No automatic retry/rollback/cleanup.

Cloudflare references:
- https://developers.cloudflare.com/workers/versions-and-deployments/
- https://developers.cloudflare.com/workers/versions-and-deployments/deployment-management/
- https://developers.cloudflare.com/workers/wrangler/commands/workers/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/configuration/secrets/
