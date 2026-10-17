# Ausmalwiese Stats Worker — exact-version module SHA-256 source (#1045)

**SOURCE ONLY / OFFLINE PROOF / LIVE BLOCKED.** This change cannot contact Cloudflare, run with credentials, install a protected operator, authorize a Worker upload or deploy, or promote source test results to authenticated LIVE evidence. The earlier `version_code_proof()` and `plan_live_mutations()` in `scripts/ausmalwiese_stats_worker_transport_v1.py` **remain blocked**; no bypass or fallback is added.

## Pinned target and request design

- Account identity: SHA-256 of **the exact 32-character lowercase account ID**, matching `3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34`. Never store/echo the actual account ID in tracked source.
- Worker: `coloring-pages-stats-v1` only; Production only. No report Worker, no other routes, bindings or account settings.
- Pinned source: `rozkalnsandris/coloring-pages@9590be4276ac1781eafe38cf662b8d224653c9aa`, `cloudflare/stats-worker.js`, Git blob SHA-1 `dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4`.
- Cloudflare provider **GET**: `https://api.cloudflare.com:443/client/v4/accounts/{account_id}/workers/workers/coloring-pages-stats-v1/versions/{version_id}?include=modules`. Require a full exact lowercase UUID, no prefix or `latest`. TLS certificate verification, 0 redirects/retries, no proxies or alternate hosts/paths in a **future independently reviewed** fixed protected HTTP collector. `fixed_get()` only returns a non-executable blueprint; this PR ships no network or credential client.

Official API: [Get Worker Version](https://developers.cloudflare.com/api/typescript/resources/workers/subresources/beta/subresources/workers/subresources/versions/methods/get/). The optional `include=modules` returns `result.modules[*].content_base64`, `content_type`, and `name`, with `result.main_module`. This is **not** the older `/workers/scripts/{script}/versions/{id}` API whose `resources.script.etag` semantics are insufficient for exact source SHA-256 proof.

## Offline module proof

The offline verifier requires an independent expected version/identity inventory, a bounded provider-shaped JSON response, and exact canonical Worker bytes supplied separately. This input inventory is still just *caller data* and is **not authenticated by the verifier**. A future trusted provider collector must separately prove account->Worker mapping, full version ID, 100% active and latest version equality, HTTP response origin/integrity and complete version metadata. No caller-provided `attested`/`authenticated` flag is accepted as authority.

1. Bound the full JSON response to 2 MiB, reject duplicate JSON keys, invalid UTF-8, nonfinite numbers, error/status responses and unknown version/module fields. Require exactly `stats-worker.js` as the sole module and `main_module`, MIME `application/javascript+module`, strict canonical base64, decoded module length 1..120000 bytes. More modules or different MIME => STOP; do not strip sourcemaps, minify, reformat or normalize newlines.
2. Bind canonical source bytes by Git's `SHA-1("blob " + bytes_length + NUL + bytes)` to pinned `dd5a2859...` before computing SHA-256. Compare SHA-256 of the **decoded provider module bytes** to SHA-256 of independently source-bound canonical bytes. Also require exact byte equality; do not accept source/response-supplied hash strings or `etag` as code proof.
3. Emit only `OFFLINE_BYTES_MATCH_NOT_AUTHENTICATED_NO_LIVE` for a successful synthetic comparison. Failure emits only fixed classifications, never raw code, headers, bindings or secrets. The synthetic unit tests use a separate fixture with patched Git blob and account fingerprint, not the real Cloudflare Worker or account ID.

## Remaining independent owner gates (all unexecuted)

1. Review and merge this source after exact-head CI/review and a new explicit MERGE command.
2. Approve, install and prove a fixed root-owned collector and distinct least-privilege credential provisioning outside Git; prohibit ambient env, checkout token, OAuth cache and protected file reads in this source task.
3. Separately authorize authenticated Cloudflare **read-only** inventory/version/module retrieval and confirm real module availability/shape. Provider incompatibility or transformed bytes => STOP, not a relaxed comparison.
4. Perform independent bindings/routes/compatibility and version/deployment checks; approve a separate owner-gated, one-use Worker Version Upload and 100% Deployment only when every prerequisite has authenticated evidence. No such mutations are possible in the current source.

No LIVE observation, route change, D1 mutation, report Worker action, redirect activation, RPi5 write, credential access or retry/rollback/cleanup occurred in #1045. A CI success proves only offline code behavior.
