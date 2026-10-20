# Ausmalwiese Drive stage sender v1

Issue: #1128

## Purpose

This source defines a project-controlled staging bridge for Coloring Pages `PUBLISH`.
It removes the runtime dependency on ChatGPT-internal `source_file_ref` / Google
Drive connector `file_uri` handoff. It does **not** replace the existing
Drive→RPi5 ingest operator.

The intended future flow is:

```text
Chat PUBLISH
→ deterministic A4 print-master preparation and validation
→ complete activity envelope sent to the trusted RPi5 sender over the authorized execution channel
→ sender verifies every byte, SHA-256, size, filename, MIME and manifest binding before mutation
→ fixed privileged wrapper stages PNG(s) first and prebuilt manifest last to Drive pending/
→ existing coloring-pages-drive-ingest pulls, verifies, imports and proves public state
```

## Envelope

The sender accepts exactly one JSON object on stdin with schema
`rozkalns.rpi5-main.coloring-pages-drive-stage-envelope.v1`.

Each activity contains one seven-digit ID and an ordered `artifacts[]` list.
Every artifact contains the exact staged filename, MIME type, SHA-256, byte
size, and base64 payload. Single-page v1 is:

```text
<id>.png
<id>.json
```

Ordered v2 is:

```text
<id>-1.png
<id>-2.png
...
<id>.json
```

The manifest is always last. All artifacts in the complete envelope are decoded
into anonymous temporary handles and validated before the first Drive write.
There is no persistent artifact spool.

## Privilege boundary

`coloring-pages-drive-stage-sender` runs as `andris` and cannot select a
Drive remote, root folder, configuration path, or arbitrary output path.

Only `/usr/local/libexec/coloring-pages-drive-stage-rcat` runs as root. The
sudo rule exposes that one wrapper only. The wrapper fixes:

- rclone: `/usr/bin/rclone`
- remote: `gdrive`
- root folder ID: `1F0pxqoRgtZl7JQVcyvYVZxKvx6eOnytn`
- subdirectory: `pending`
- config path: `$OWNER_HOME/.config/rclone/rclone.conf`

The wrapper verifies only config file metadata. It never reads or prints
credential contents.

Before staging, the sender takes one lock and performs one whole-batch
collision check. Each upload is rechecked immediately before `rclone rcat`
and verified afterwards by exact filename and byte size.

## Retry and failure semantics

The wrapper pins `--retries 1`, `--low-level-retries 1`, and
`--retries-sleep 0s`. The sender contains no application retry loop.

After the first upload attempt, any failure is terminal for that invocation:
no retry, rollback, cleanup, overwrite, alternate provider, ingest call, or
public verification is attempted.

Drive is still transport only. Successful staging is not publication success.

## Installation and activation

Merging this source does not install or activate anything.

The reviewed installer can later install the sender, wrapper, sudoers entry,
state directory and lock only after a separate explicit LIVE authorization
bound to the exact merged RPi5_main SHA. The installer itself does not execute
rclone, write Drive, read credential content, change rclone configuration,
invoke ingest, or change systemd.

Before this sender may become part of the normal Coloring Pages `PUBLISH`
contract, activation must separately prove:

1. exact installed sender/wrapper/sudoers source identity;
2. expected owner/mode for the sender state and rclone config metadata;
3. required rclone capabilities without exposing config contents;
4. one explicitly authorized non-production canary;
5. a reviewed Coloring Pages contract update that selects this sender as the
   staging surface.

The existing `coloring-pages-drive-ingest` remains unchanged and pull-only.

## References

- https://rclone.org/commands/rclone_rcat/
- https://rclone.org/commands/rclone_lsf/
- https://rclone.org/docs/#retries-int
- https://developers.google.com/workspace/drive/api/guides/manage-uploads
