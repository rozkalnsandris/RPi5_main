# Control Phase 5 RPi5 signed-observation runtime delivery source

Issue #501 closes the source gap between the already-reviewed RPi5 Phase 5 visibility producer, exact signed transport, protected-credential Ed25519 signer and a later separately authorized one-shot delivery to Control. This document is source authority only. It does not prove or authorize host installation, production key access, runtime activation or a live HTTP request.

## Reviewed cross-repository identity

This source package is deliberately pinned to Control source `42d2087fc42079cdcfb4a2a1ecbc255f0284080e`. At review time the relevant Control blobs are:

- `src/shared/production-visibility.ts`: `5546c0fb37072c5903d6e7c6aa02a9eea7baf43d`;
- `src/shared/rpi5-observation-transport.ts`: `cae7864f9a1053b5141353ac192c9c2d512f955a`;
- `src/shared/phase5-rpi5-signer-handoff.ts`: `a04c34949f7fbbed3fb8eafc37ddca1d5da55842`;
- `src/worker/rpi5-observation-route.ts`: `d613c11fbbd32e61062ffd8ea6054d4e86ea6f16`.

The producer and transport blob identities are unchanged from the earlier reviewed source contract, while their source-SHA provenance is rebound to the current reviewed Control source. A later Control source SHA is rejected until cross-repository compatibility is reviewed again.

## Strict public-safe handoff

`ops/lib/deploy_executor/control_phase5_signer_handoff.py` mirrors `PHASE5_RPI5_SIGNER_HANDOFF_V1`. It requires the exact field set, Control repository/Worker identity, deployment/version UUIDs, traffic `100`, ingest `PRESENT_TRUE`, observation protocol, public `key_id`, fixed `RPi5_main` receiver/lane/owner and all four no-authority flags. The canonical millisecond UTC `generated_at` value must be no more than 300 seconds old and must not be future-dated.

The handoff is evidence only. The delivery path separately binds it to an exact expected Control source/deployment/version/key tuple, and only the reviewed Control source SHA is accepted. It never grants LIVE, cross-repository write or RPi5 runtime mutation authority.

## One-shot source entrypoint

`ops/bin/rpi5-control-phase5-observation-deliver` reads one strict JSON object from stdin with exactly:

- `handoff` — the fresh strict Control handoff;
- `expected` — public exact Control/deployment/version/key and project/repository/main identities frozen by the later operation;
- `visibility` — the existing ten-field sanitized production-visibility object.

There is no caller field for URL, path, method, header names, command, shell, filesystem path or arbitrary environment. Input is bounded to 64 KiB.

`--validate-only` validates the entire public input/provenance chain and emits a public-safe `SOURCE_INPUT_READY` receipt with `network_request=NO`, `credential_access=NO` and `live_authority=NOT_GRANTED`. It does not load the protected signing credential and does not open a network connection.

Without `--validate-only`, the source path composes the existing normalizer, transport and protected-credential signer. The entrypoint itself must not be executed against production until a later exact Composite LIVE authorization permits the credential/runtime/delivery scope.

## Fixed Control transport

The only production destination in source is:

`https://control.rozkalns.net/api/rpi5/observation`

The client uses TLS certificate verification, a five-second timeout, `POST`, the exact five reviewed `x-rpi5-observation-*` metadata headers, `Content-Length`, and the exact signed payload bytes. It does not follow redirects or accept a caller-selected origin/path. HTTP `3xx`, `4xx`, `5xx`, transport errors, timeout, oversized/malformed response or any success body other than exactly `{"status":"AUTHENTICATED_AND_CLAIMED"}` fails closed.

The public success receipt contains only public identities, project/source identities, delivery ID/time and HTTP `202`. It contains no signature text, private/public key bytes, credential path/content, token, raw response, protected configuration or OpenSSL diagnostic.

## LIVE sequence remains separate

After this source package is merged and exact-main CI is green, a future RPi5-owned operation must freshly revalidate current repository rules and exact identities. The intended sequence is:

1. obtain fresh Control GET-only post-activation evidence and a fresh `PHASE5_RPI5_SIGNER_HANDOFF_V1` manifest;
2. run the source entrypoint in `--validate-only` mode against the exact sanitized observation input;
3. STOP for one bounded Composite LIVE authorization that explicitly names the exact RPi5 SHA/target, protected credential/key prerequisite, one-shot delivery mutation class and exclusions;
4. only through that reviewed envelope, satisfy any separately approved key/runtime prerequisite and execute one exact signed observation delivery;
5. require the public-safe delivery receipt and then perform Control-side read-only reconciliation of the accepted observation/projection;
6. on any error or ambiguity after the first authorized mutation, preserve sanitized evidence and STOP with no undeclared retry, rollback, cleanup or alternate path.

Source merge never authorizes step 3 or later. This source package installs no unit, service, timer, credential, package or host configuration and performs no production request by itself.
