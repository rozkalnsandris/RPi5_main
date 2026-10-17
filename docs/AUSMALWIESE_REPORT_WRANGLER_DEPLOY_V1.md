# Ausmalwiese Report Worker — Wrangler deploy source contract (#1048)

**SOURCE ONLY. NO MERGE. NO LIVE. NO CLOUDFLARE REQUEST. NO CREDENTIAL OR SECRET ACCESS.**

This outcome replaces the older custom REST/multipart deployment direction with one
small, reviewed Wrangler deployment contract for `coloring-pages-report-v1`. It
does not install or run Wrangler, read a secrets file, contact Cloudflare, deploy
the Worker, send mail, or mutate the RPi5 host.

## Frozen application provenance

The deployment source is owned by `rozkalnsandris/coloring-pages`:

- commit: `699c036b7f952aa98be06e166a9705069b7e9eb2`
- Worker: `cloudflare/report-worker.mjs`
- Worker Git blob: `6d2359752d12f4a40847008fc7fdcc457124e893`
- Wrangler config: `cloudflare/wrangler.report.json`
- config Git blob: `a49576aa391015e7b0e867bb7eef03c7f90d0987`
- target Worker: `coloring-pages-report-v1`
- Wrangler: `4.135.0`

The reviewed config keeps `workers_dev=false`, `preview_urls=false`,
`no_bundle=true`, exactly four report routes, exactly four required secrets, and
two distinct rate-limit namespaces. Account-wide namespace uniqueness is a
future read-only LIVE preflight; source equality alone does not prove it.

## Exact reviewed config

Routes:

- `ausmalwiese.de/api/report`
- `ausmalwiese.de/api/report/config`
- `www.ausmalwiese.de/api/report`
- `www.ausmalwiese.de/api/report/config`

Required secret names:

- `TURNSTILE_SITE_KEY`
- `TURNSTILE_SECRET`
- `BREVO_API_KEY`
- `REPORT_TO`

Rate limiting:

- `REPORT_RATE`: namespace `2067894450`, 12 / 60 s
- `REPORT_DUP`: namespace `2051617019`, 1 / 60 s

The source validator rejects any extra/wildcard route, missing or extra secret
name, wrong Worker/main, workers.dev or preview exposure, unexpected config key,
namespace drift, rate drift, or a non-10/60-second rate period.

## Future one-shot deploy shape

`scripts/ausmalwiese_report_wrangler_deploy_v1.py` contains the reviewed fixed-purpose future launcher plus the command/verification validators. The current #1048 activation does **not** authorize calling its `--deploy` mode. A later separately authorized runtime invocation must supply an exact `coloring-pages` checkout root and the owner-bound protected secrets-file path.

The fixed shape is equivalent to:

```text
npx --yes wrangler@4.135.0 deploy --config cloudflare/wrangler.report.json --name coloring-pages-report-v1 --no-bundle --strict --secrets-file <owner-bound-absolute-protected-path> --tag git:699c036b7f952aa98be06e166a9705069b7e9eb2 --message <exact-source/config-provenance>
```

Cloudflare documents `--secrets-file` for uploading JSON or `.env` secrets
alongside `wrangler deploy`; required names declared through `secrets.required`
are validated during deploy. `--strict` is kept so non-interactive deployment
fails rather than silently overriding conflicting remote state.

Before a future dispatch, the launcher checks the checkout HEAD equals the pinned application commit, the two Git tree blobs equal the pinned Worker/config blobs, the two working-tree paths are unchanged, the parsed config equals the closed reviewed shape, and the secrets file is an absolute single-link regular file owned by the executing UID with mode `0400` or `0600`. It reads only secrets-file metadata; Wrangler itself is the future consumer of secret contents.

The launcher then verifies the exact `wrangler@4.135.0` selector reports version `4.135.0` and permits exactly one deploy dispatch. A non-zero or ambiguous deploy result becomes terminal `DEPLOY_DISPATCH_UNKNOWN`; the source contains no automatic retry, rollback or cleanup.

A future LIVE authorization must bind the exact source commit/blobs, launcher release, Wrangler version, target Worker, protected secrets-file path and one deployment. This source issue does not authorize that operation.

## Read-only post-deploy verification contract

After a separately authorized deployment, verification is read-only. The source
can produce only these fixed inspection shapes:

- `wrangler versions list --json`
- `wrangler deployments list --json`
- `wrangler versions view <exact-version-id> --json`
- `wrangler secret list --format json`
- GET `https://ausmalwiese.de/api/report/config`

The sanitized report snapshot must prove:

- the latest version is the only active version at exactly 100%;
- version tag/message bind the exact application commit, Worker blob and config blob;
- exactly the four report routes are present;
- exactly four `secret_text` names and the two `ratelimit` bindings are present;
- rate-limit namespaces and policies equal the reviewed config;
- `/api/report/config` returns HTTP 200 and exposes a site key.

The source deliberately does **not** implement a generic Cloudflare REST client.
Any future collector that supplies this snapshot remains separately reviewed and
read-only.

## Stats no-effect guard

`coloring-pages-stats-v1` is a protected neighbor. A future LIVE preflight must
capture a sanitized Stats snapshot immediately before the report deploy and
again afterwards. The source accepts only exact pre/post equality for:

- latest and single 100% active version;
- route fingerprint;
- binding fingerprint;
- settings fingerprint.

Any difference is `STATS_DRIFT` and the verification fails closed. This issue
does not authorize fixing or redeploying Stats.

## Official provider references reviewed 2026-10-17

- https://developers.cloudflare.com/workers/wrangler/commands/workers/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- https://developers.cloudflare.com/workers/configuration/routing/routes/
- https://developers.cloudflare.com/workers/wrangler/install-and-update/

Cloudflare currently documents `namespace_id` as a positive integer encoded as a
string, with rate-limit periods restricted to 10 or 60 seconds. Distinct
namespace IDs avoid shared counters across bindings.

## Offline checks

```text
python3 scripts/ausmalwiese_report_wrangler_deploy_v1.py --check-contract
python3 tests/test-ausmalwiese-report-wrangler-deploy-v1.py
```

Passing these checks proves only source consistency. The `--deploy` entrypoint is deliberately present for later reviewed installation/use but was not invoked by #1048. Passing source checks does not prove current
RPi5 installation state, Cloudflare account state, namespace uniqueness, secret
availability, Turnstile/Brevo readiness, route activation, mail delivery, or LIVE
authorization.
