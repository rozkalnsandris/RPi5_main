# Ausmalwiese Stats legacy-ID trusted runtime v1 — issue #1417

SOURCE ONLY. INSTALLATION, CREDENTIAL ACCESS, CLOUDFLARE REQUESTS, D1 READ/WRITE AND LIVE ARE NOT AUTHORIZED.

## Outcome

This source turns the merged #1412 planner into an installable, fail-closed runtime boundary without copying the 30 aliases or six UPDATE statements. The runtime dynamically loads the exact #1412 planner only after verifying these Git blobs from the trusted RPi5_main checkout:

- planner: fb0c39fd552ec55e3fbb4310fe70dfee42e4e1c4
- migration contract: c571dc6efc702ecf5f933aa58f3f7a59e5db02e9
- alias artifact: 2e20a2a7a7e716274934a0eb662091150ef55e7f

The fixed installed entrypoint is /usr/local/sbin/rpi5-ausmalwiese-stats-legacy-id-d1-migrate. A future LIVE command must bind the exact current reviewed RPi5_main main SHA. The runtime requires that checkout to be clean main with the trusted origin, requires the installed bytes to equal the exact runtime bytes at that HEAD, and rejects dependency/contract drift.

## Credential gate

No compatible reviewed Stats D1 Read+Write credential provider exists in the current source baseline. Therefore the runtime contract deliberately sets:

credential_provider.status = REQUIRED_NOT_ESTABLISHED

and runtime preflight stops with CREDENTIAL_PROVIDER_REQUIRED before reading a credential or contacting Cloudflare. The fixed future provider path is /usr/local/libexec/rpi5-ausmalwiese-stats-d1-credentials-v1, but this issue does not implement, provision or authorize that provider. A later owner-gated source outcome must establish exact provider bytes, the exact database/account binding and exactly D1 Read + D1 Write capability before the runtime contract can change to ESTABLISHED.

Tokens are never accepted through argv, environment, GitHub, logs or operator output.

## D1 transport

The reviewed API target is fixed to HTTPS api.cloudflare.com and
POST /client/v4/accounts/{account_id}/d1/database/f8ac8f1d-a230-4bc4-af13-557c1b91b273/query.

The request body is always {"batch":[...]}.
Read preflight/post-verification contains exactly the 24 statements emitted by #1412 read_plan. The only mutation body contains exactly the six statements emitted by #1412 migration_operation. There is no caller-selected SQL, database, table, endpoint or batch size.

Transport uses verified TLS, disables ambient proxies and redirects, has zero automatic retries, a 12-second request bound and a 1-MiB response limit. Cloudflare documents the D1 query endpoint batch body at:
https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/

Cloudflare documents that D1 batched statements run as one SQL transaction and that a failing statement rolls back the entire batch:
https://developers.cloudflare.com/d1/observability/find-expensive-queries/

After the mutation request is dispatched, any transport/response ambiguity or failed post-verification is terminal UNKNOWN/STOP. There is no automatic retry, rollback or cleanup.

## Verification sequence

Future operation order is fixed:

1. install the reviewed runtime under a separate exact root-install authorization;
2. establish a separately reviewed protected D1 Read+Write credential provider;
3. run fresh protected runtime preflight: exact installed/source bytes, exact D1 identity, exact six table/PK shapes, zero target-ID rows, sanitized legacy aggregates;
4. owner-authorize exactly one D1 batch using the returned baseline SHA-256;
5. revalidate source immediately before dispatch;
6. dispatch exactly one six-entry mutation batch;
7. run a fresh 24-query sanitized post-read and call #1412 validate_post;
8. only after success proceed to a separately authorized RPi5 catalog/media ID cutover.

Public output is limited to fixed status/reason values, statement count and evidence digests. Visitor hashes, timestamps, raw rows, account IDs, tokens and raw Cloudflare responses are never emitted.

## Source-only checks

    python3 scripts/ausmalwiese_stats_legacy_id_runtime_v1.py --check-contract
    python3 tests/test-ausmalwiese-stats-legacy-id-runtime-v1.py

Source merge does not install the runtime and does not make the credential provider available.
