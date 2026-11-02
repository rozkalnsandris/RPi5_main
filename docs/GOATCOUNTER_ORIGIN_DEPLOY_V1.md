# Coloring Pages origin counting: opt-in trusted deployment

Source outcome: RPi5_main #1346. **Uninstalled, source-only support.** The default
registry and default Coloring Pages Compose file remain byte-for-byte unchanged.
Merging this implementation does not select, build, publish, install or activate
an origin-counting image. The private collector and ADMIN reporting must not be
reinstalled by this procedure.

## What ordinary reconciliation does

The installed target may explicitly contain an `origin_counting` object. It is
accepted only for `coloring-pages-public-rpi5`, consumer
`rozkalnsandris/coloring-pages`, project/service
`coloring-pages-public/coloring-pages`, and the exact generated adapter. All
other targets retain the original path. No runtime image/path/group CLI is added.

The target's `image` continues to identify the ordinary app's production pointer.
For an opted-in target the reconciler compares that pointer to the reviewed
`base_digest` **before** any Compose command or override write. If different, it
returns `HOLD_ORIGIN_PAIR_REQUIRED`, records `REVIEWED_DERIVATIVE_REQUIRED`, exits
nonzero and retains the running deployment and last success receipt. It does not
install the ordinary image, report a successful update, or publish a derivative.
HOLD can be re-evaluated on a later ordinary tick; it is not a post-mutation
failure or permission for a repair.

When the pair matches, both immutable image configurations must prove linux/arm64,
the exact application source revision, target and shared-workflow labels. The
separately named derivative must additionally prove the reviewed recipe/base
labels, UID 101 and the baked origin Nginx command. The reconciler then uses only
`ghcr.io/rozkalnsandris/coloring-pages-origin@sha256:<digest>` in its existing
bounded pull/up/health/receipt path. It never discovers a derivative mutable tag.
The installed full Compose is byte-compared with the bounded renderer and its
registry hash before discovery. The four variant service fields are image,
platform, supplementary group and volumes (one additional socket-directory bind).

The original loopback port, public-content bind, read-only root, tmpfs,
no-new-privileges, dropped capabilities, health check and restart policy remain.
There are no credentials, SQLite, Docker socket, environment values or arbitrary
host paths in the generated adapter. The socket directory is
`/run/ausmalwiese-pageview` on both sides, read-only, `create_host_path: false`.
Read-only mounting a directory does not prohibit connecting to its Unix socket.
The supplementary group supplies filesystem access; it does **not** change the
primary identity reported by `SO_PEERCRED`.

A successful receipt includes the derivative digest/ref, original pointer digest
and canonical profile hash. Repeating the exact pair/profile is a no-op. A changed
profile cannot be skipped merely because the image digest is unchanged. Once a
successful receipt records opt-in, removing the profile is rejected before
mutation; clearing/replacing receipts is not an ordinary disable procedure.
Post-pull failures retain the existing persistent STOP behavior, with no automatic
retry, rollback or cleanup. Do not clear a STOP to make an upgrade proceed.

## Strict profile and offline bundle

The optional profile is a strict object with these fields; no additional fields
are accepted:

| Field | Meaning |
| --- | --- |
| `schema` | `rozkalns.coloring-pages.origin-profile.v1` |
| `application_source_sha` | Exact 40-character lowercase app revision from base image metadata |
| `base_digest` | Ordinary production pointer digest, possibly an OCI index |
| `base_platform_digest` | Its unique linux/arm64 image manifest digest |
| `recipe_source_sha` | Accepted recipe source `8d0de541e03f2db1196fb89569d549fb2294abfb` |
| `derivative_digest` | Resulting derivative **arm64 image manifest** digest, not the attestation index |
| `architecture` | `linux/arm64` |
| `socket_group` | Explicit positive decimal container-visible supplementary GID, no leading zero |
| `provenance_sha256` | SHA-256 of canonical JSON provenance statement |
| `peer_evidence_sha256` | SHA-256 of canonical JSON observed peer/mapping evidence |

Canonical JSON hashing uses sorted keys, separators `(',', ':')`, Python's default
ASCII escaping and no trailing newline. Image digests include `sha256:`; evidence
hashes are 64 lowercase hex characters. Request-file SHA binds its **exact bytes**.
These hashes bind reviewed evidence; they do not authenticate arbitrary statements.

`scripts/prepare-goatcounter-origin-deploy-v1.py` is non-root, offline and emits one
JSON bundle to stdout. It invokes no subprocess, network, Docker, host probe or
installer. Its only inputs are the explicit bounded regular request file and
canonical source registry/default adapter in its checkout. Symlink/FIFO requests,
duplicate JSON keys, request hash mismatch, stale observations, altered default
adapter, unknown profile and conflicting metadata are refused. Output is emitted
only after all checks pass. No output file or installed configuration is opened.

```sh
python3 scripts/prepare-goatcounter-origin-deploy-v1.py \
  --request reviewed-request.json \
  --request-sha256 <independently-reviewed-exact-request-sha256> \
  --source-sha <exact-reviewed-RPi5_main-commit>
```

Before using that command, independently verify that the checkout and entrypoint
match the reviewed RPi5 commit; `--source-sha` is an expected binding, not proof of
the executable's provenance. Run from a source workspace, never feed it protected
installed configuration. The result contains `registry`, full `compose`, its hash,
profile hash and `runtime_authority: false`. It is a preparation artifact, not an
installer authorization. Repeated identical input/time eligibility yields identical
output. No generated production bundle belongs in source control.

The request schema `rozkalns.origin-preparation.v1` has exactly:
`schema`, `rpi_source_sha`, `registry_sha256`, `profile`, `base_config`,
`derivative_config`, `base_manifest_raw`, `provenance`, `peer_evidence`.
The two configs are public OCI image config objects (`os`, `architecture`,
`config.Labels`, and derivative `User`, `Entrypoint`, `Cmd`). `base_manifest_raw`
is the exact raw public manifest/index text: its byte digest must equal
`base_digest`; its unique arm64/v8 descriptor must equal `base_platform_digest`.
For a single image manifest the two digests must agree. The source registry hash
binds the complete canonical source registry; every unrelated target is preserved.

The provenance input is a complete BuildKit in-toto Statement/v0.1 with SLSA v0.2
predicate, generated using `mode=max,version=v0.2`. Checks bind its arm64 derivative
subject, `buildType`, immutable remote Git configSource URI ending in the recipe
SHA, source digest, `deploy/Dockerfile.origin-counting`, exact
`build-arg:APPLICATION_IMAGE`, and arm64 base material digest. Percent-encoded purl
characters are decoded for comparison. A local-context VCS label, unknown schema,
mutable recipe URI or missing material is not accepted as equivalent evidence.
The builder platform can differ from the output platform; it is not used as proof
of arm64. The reader does not verify registry signatures or builder identity:
reviewers must authenticate the publication job/attestation and its immutable
subject before independently approving the request hash. Do not fabricate or edit
an attestation to fit the parser. If a publisher emits a different representation,
stop and review that format with a real public fixture before source changes.

`peer_evidence` schema `rozkalns.origin-peer-evidence.v1` contains exactly `schema`,
`host` (`rpi5`), `observed_at` (UTC `YYYY-MM-DDTHH:MM:SSZ`), `image_ref`,
`container_uid` (101), `container_primary_gid`, `host_peer_uid`, `host_peer_gid`,
`collector_allowed_uid`, `collector_allowed_gid`, `container_socket_group`,
`host_socket_gid`, `mapped_socket_gid`. Numeric IDs must be explicit positive
integers; the supplementary container group is the same decimal string as the
profile. Observed primary peer IDs must equal collector allowlist IDs, and the
observed mapped socket GID must equal the host socket GID. No identity mapping is
inferred. Evidence must name the exact derivative image and be no older than 24
hours or in the future. It must come from separately authorized bounded checks;
the preparer neither performs those checks nor proves a statement is truthful.
Fresh installation preflight must repeat the binding checks if anything changed.

## Future publication, installation and update procedure

These steps require their own exact authorization. They are documentation, not
commands performed by #1346 or an automatic release workflow.

1. Select the exact current ordinary production digest, source revision and
   arm64 descriptor. Review its shared-workflow labels and build/test provenance.
   Review the accepted recipe and generator at the pinned Coloring Pages source.
   A changed recipe requires a source review updating the accepted recipe pin.
2. Under a separate bounded publication decision, build from the immutable remote
   Git context `https://github.com/rozkalnsandris/coloring-pages.git#<recipe-sha>`,
   Dockerfile `deploy/Dockerfile.origin-counting`, `--platform linux/arm64`,
   `APPLICATION_IMAGE=ghcr.io/rozkalnsandris/coloring-pages@<base_digest>` and
   `--provenance=mode=max,version=v0.2`. Add labels
   `io.rozkalns.origin.base-digest=<base_digest>` and
   `io.rozkalns.origin.recipe-revision=<recipe-sha>`; preserve inherited app source,
   target and shared-workflow labels. Publish only to the separate `coloring-pages-origin`
   repository, never change the ordinary production tag. Record the resulting
   arm64 manifest digest and authenticated publication/attestation evidence.
   Source tests here do not prove a published arm64 artifact exists or works.
3. Verify that exact derivative with the existing isolated application wire/probe
   suite, including importer/Like/Print/QR/campaign compatibility. No public test
   event is implied. Obtain fresh, separately authorized rpi5 identity, socket,
   collector, primary-peer and group-mapping evidence for that derivative (use an
   explicitly scoped isolated candidate if needed). Retain only sanitized facts.
4. Complete the actual server-request-flow notice/assessment, then prepare and
   review the request and generated bundle against the exact RPi5 source. A first
   deployment is also **public collection activation**; installing a valid profile
   into a running reconciler can cause deployment on its next tick. Do not treat
   profile/registry installation as harmless private provisioning.
5. Prepare one exact bounded LIVE plan: fresh installed helper/registry/identity/
   Compose/receipt baseline; target timer and in-flight reconciliation controls;
   trusted helper upgrade; generated adapter and target registry materialization;
   one explicitly authorized target reconciliation; health, image, socket and
   separately authorized event verification. Preserve other target entries and
   their live installed baselines. Replacing the whole installed registry from a
   source bundle without comparing every other target is forbidden. Keep the same
   per-target lock across the critical replacement/reconcile boundary, and quiesce
   both the target-specific and any generic all-target scheduler that can race it.
   Install helper/adapter before the profile, using root-owned non-writable files;
   update the installed source identity consistently. No generic first-installer
   rerun, manual overlay, credential provisioning, collector reinstall or implicit
   rollback/cleanup is needed or authorized. The exact later LIVE plan must name
   paths, hashes, lifecycle operations, limits and failure recovery before execution.
6. A later ordinary app publication automatically causes HOLD until a matching
   reviewed derivative exists. Repeat publication/provenance/peer preparation for
   the new pair; replace only this target's profile/adapter under separate exact
   authorization and unchanged-baseline checks. Reconcile, verify, retain the new
   receipt. The test suite covers this transition and subsequent idempotency.
   This deliberately delays ordinary app/security updates while a pair is missing;
   operators must monitor HOLD and prepare the matching pair promptly. Never use
   the ordinary image as an automatic fallback or clear receipts to bypass opt-in.

The current installer is not widened into an arbitrary profile installer. The
new profile functions live inside the existing trusted helper module, so helper
installation has no hidden extra Python-module dependency. This PR adds no
registry publisher, timer, service, package, permissions or credential workflow.

## Measurement and remaining release evidence

Origin counting measures eligible server-received detail HTTP requests, affected
by cache misses/revalidation, repeats/bots and later response failures. It is not a
count of people, successfully rendered pages, or cached browser views. No new
browser analytics request is introduced by this variant. Existing legacy Stats
and other access/logging paths still need their own actual-flow review.

Private ADMIN periods are **UTC today / 7 / 30 / 365 days**, and retained history
is 365 days. Older Berlin/all-time design wording is superseded. The dated private
[ADMIN connection receipt](https://github.com/rozkalnsandris/RPi5_main/pull/1339#issuecomment-6586098161)
proved four valid empty reports, not public counting. It is not evergreen host,
peer, socket, edge or logging evidence. [Coloring Pages #158](https://github.com/rozkalnsandris/coloring-pages/pull/158)
remains the separate actual-flow notice/assessment prerequisite. No privacy/legal
certification, public collection state or LIVE completion is claimed here.

## Source validation and references

Run `python3 tests/test-goatcounter-origin-deploy-v1.py`,
`python3 tests/test-simple-deploy-v1.py` and
`python3 tests/test-simple-deploy-pointer-failure-926.py`; the new suite is also in
`make validate` and the existing target-source CI workflow. All commands are
synthetic/offline. They cover default behavior, profile/metadata/provenance and
peer refusals, bounded Compose delta, HOLD, pair advancement, no-op, profile
removal prevention and persistent post-mutation STOP. They do not execute Docker.

- [Application contract at accepted source](https://github.com/rozkalnsandris/coloring-pages/blob/8d0de541e03f2db1196fb89569d549fb2294abfb/docs/GOATCOUNTER_ORIGIN_APP_376.md)
- [Compose service semantics](https://docs.docker.com/reference/compose-file/services/)
- [Buildx metadata inspection](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/)
- [Docker provenance](https://docs.docker.com/build/metadata/attestations/slsa-provenance/)
- [BuildKit SLSA field definitions](https://docs.docker.com/build/metadata/attestations/slsa-definitions/)
