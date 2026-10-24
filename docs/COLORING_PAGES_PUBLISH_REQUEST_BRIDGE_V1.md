# Ausmalwiese PUBLISH request bridge v1

## Goal

Keep normal publication short after the direct Google Drive upload path.

Normal path:

    PUBLISH
    -> prepare + validate A4 master(s)
    -> upload PNG page(s) only to Drive pending/
    -> write one small request JSON containing the validated manifest(s)
    -> write one small ready marker
    -> existing coloring-pages-drive-ingest runs on RPi5
    -> read one small result JSON
    -> PASS

The bridge removes the generic Remote Desktop Commander shell hop from the
normal PUBLISH path. It does not move image bytes, upload to Drive, or replace
the existing ingest/import operator.

Machine contract:
    ops/contracts/coloring-pages-publish-request-bridge-v1.json

Dispatcher source:
    ops/bin/coloring-pages-publish-request-dispatcher

Installed dispatcher:
    /usr/local/bin/coloring-pages-publish-request-dispatcher

## Why this stays fast

Image bytes continue to use the direct Google Drive connector. The request
bridge transfers only a tiny JSON control message plus a tiny ready marker.
There is no Base64 media transfer over RDC and no second media upload.

The existing Drive ingest operator still performs the actual Drive pull,
SHA/size verification, immutable importer execution and public proof.

## Fixed state layout

    /srv/coloring-pages-content/state/publish-request-bridge/
      .lock
      incoming/
        batch-<32hex>.json
        batch-<32hex>.ready
      claimed/
        batch-<32hex>.json
        batch-<32hex>.ready
      results/
        batch-<32hex>.result.json

All bridge state is non-secret and owned by andris. Requests contain only page
IDs, hashes, sizes, ordered page identities and the already-validated publication
manifest metadata. They never contain PNG bytes or credentials.

## Chat handoff

After every required Drive PNG page upload passes connector response/readback
verification, PUBLISH creates one random 32-lowercase-hex batch_id. Normal
PUBLISH does not upload a JSON manifest to Drive; that small manifest is carried
inside the bridge request.

The request file is written completely first. It uses schema
rozkalns.rpi5-main.coloring-pages-publish-request.v1 and contains 1-20
activities.

A v1 activity contains:
- kind = v1
- id = exact seven-digit publication ID
- expected_sha256 = exact 64-lowercase-hex print-master digest
- expected_size = exact byte size
- manifest = complete validated v1 manifest object matching the same ID/SHA/size

A v2 activity contains:
- kind = v2
- id = exact seven-digit activity ID
- expected_pages = 2-12 ordered entries with index, sha256 and size_bytes
- manifest = complete validated v2 manifest object matching the same ordered pages

Only after the complete request file exists, write the matching ready marker
whose content is exactly the batch_id.

The normal Chat transport for these two tiny files is a bounded file write to
the exact fixed paths. Do not invoke start_process for the publication happy
path and do not send image bytes through this bridge.

## Claim and no-retry behavior

The systemd path unit watches only incoming ready markers.

Before any ingest operator call, the dispatcher:
1. checks the request and marker are regular non-symlink files owned by the
   service user and not group/world writable;
2. verifies the ready marker matches the filename batch_id;
3. moves the ready marker into claimed;
4. moves the request into claimed;
5. validates the complete strict JSON request and each inline manifest;
6. invokes /usr/local/bin/coloring-pages-drive-ingest using an argv array with
   the manifest passed only as bounded `--manifest-json` data.

Moving the ready marker first removes the automatic trigger. A claimed request
is never moved back into incoming.

If any activity fails, the dispatcher stops the batch immediately, records the
exact already-succeeded subset and failed ID, and writes one result. It does not
retry, roll back, clean up, requeue, switch upload surfaces or invoke a second
operator.

## Result

PUBLISH reads:

    /srv/coloring-pages-content/state/publish-request-bridge/results/
    batch-<batch_id>.result.json

The result schema is
rozkalns.rpi5-main.coloring-pages-publish-request-result.v1.

PASS records the exact succeeded IDs and whether the trusted ingest operator
returned PASS or ALREADY_PROCESSED. FAIL records the already-succeeded subset,
failed ID when known, and one sanitized error string.

Terminal publication success still depends on the existing trusted ingest
operator verification for every requested activity.

## systemd

Source units:
- ops/systemd/coloring-pages-publish-request-bridge.path
- ops/systemd/coloring-pages-publish-request-bridge.service

The path unit watches only the fixed incoming ready-marker glob. The oneshot
service runs as andris and calls only:

    /usr/local/bin/coloring-pages-publish-request-dispatcher --once

No shell command string is supplied by ChatGPT.

## Installer

Source:
    scripts/install-coloring-pages-publish-request-bridge-v1.sh

The installer is a separately owner-authorized LIVE operation. It requires an
exact clean RPi5_main/main SHA, accepts only the reviewed predecessor/current
operator and dispatcher identities, creates only bounded bridge state, installs
the exact current ingest operator plus dispatcher and two systemd units, and
enables the path unit.

It does not read/change credentials, change sudoers, upload to Drive, run
rclone, run Docker, import content, deploy the application, or change network
or Cloudflare state.

Source merge alone does not install or enable anything.

## Authority

A fresh owner PUBLISH remains required for every request. The bridge is only a
transport/execution adapter for that already-bounded publication authority.

Separate owner authorization is required once to install/enable the bridge on
RPi5. Merge alone is not LIVE authorization.
