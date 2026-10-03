# Coloring Pages Drive ingest operator v1

## Purpose

Provide one bounded RPi5 operator for the approved ChatGPT → Google Drive → RPi5 content path without exposing the root-protected rclone configuration and without changing the application deployment.

Tracked source:

```text
ops/bin/coloring-pages-drive-ingest
```

Intended installed command:

```text
/usr/local/bin/coloring-pages-drive-ingest
```

Source merge does not install or execute this operator.

## Why the canary failed operationally

The first integrity canary proved that Google Drive preserved the PNG bytes exactly, but `sudo rclone copyto ... /tmp/file` created the local destination as `root:root 0600`. A later hash executed as `andris` therefore failed with permission denied.

The reviewed correction does not change ownership after download. Instead:

1. the operator runs as `andris`;
2. it creates the staging file itself with `O_CREAT|O_EXCL|O_NOFOLLOW` and mode `0600`;
3. it opens that file descriptor before privilege elevation;
4. only `sudo -n /usr/bin/rclone ... cat` runs as root;
5. rclone writes the Drive object to the already-open stdout descriptor.

The resulting file remains `andris:andris 0600`. No `chown` repair is part of the workflow.

This follows rclone's documented `cat` model: a selected remote object is emitted to stdout.

References:

- https://rclone.org/commands/rclone_cat/
- https://rclone.org/drive/
- https://www.gnu.org/software/coreutils/manual/html_node/mv-invocation.html

## Fixed Drive boundary

The operator does not accept a Drive folder or remote from the caller.

Reviewed values:

```text
remote          gdrive:
root folder id  1F0pxqoRgtZl7JQVcyvYVZxKvx6eOnytn
queue path      pending/
config          <owner-home>/.config/rclone/rclone.conf
config metadata root:andris 0600
```

The exact root folder ID is passed through rclone's Drive `root_folder_id` option, restricting the operator's namespace to that reviewed hierarchy.

The operator never reads or prints the rclone config itself. It checks only file metadata, then lets root rclone consume the existing configuration.

The operator is read-only toward Drive. It does not upload, rename, move, archive or delete Drive objects.

## Invocation

The only content-selection arguments are:

```bash
coloring-pages-drive-ingest \
  --id aviator-pup-001 \
  --expected-sha256 <64-lowercase-hex> \
  --expected-size <bytes>
```

These values must be bound by the fresh owner LIVE authorization for the exact approved image.

The caller cannot provide:

- a Drive folder;
- a Drive filename;
- an rclone config;
- an alternate remote;
- importer metadata;
- an importer image or entrypoint.

The two Drive filenames are derived from the ID:

```text
pending/<id>.png
pending/<id>.json
```

Before the first local mutation, a normal non-`--fast-list` `rclone lsf` requires exactly one occurrence of each name.

## Manifest validation

The manifest must use:

```text
rozkalns.coloring-pages.drive-staging-manifest.v1
```

Unknown keys are rejected.

The manifest ID, SHA-256 and byte size must exactly match the owner-bound CLI arguments. This prevents an untrusted or accidentally replaced Drive manifest from changing which content was authorized.

The remaining metadata is bounded to the existing Coloring Pages importer model:

- title: non-empty, one line, maximum 128 characters;
- character: optional, one line, maximum 128 characters;
- category: non-empty, one line, maximum 128 characters;
- age: `3-6` or `4-8`;
- difficulty: `easy`, `normal` or `detailed`;
- language: `de`;
- source kind: `chatgpt-generated-png`;
- approval class: `explicit-owner-chat-approval`.

Manifest size is capped at 64 KiB. PNG size is capped at 20 MiB.

## Host staging

Installer-owned scaffold:

```text
/srv/coloring-pages-content/state/drive-ingest/  andris:andris 0755
└── .lock                                         andris:andris 0600
```

Per-ID state:

```text
<id>.manifest.partial
<id>.manifest.json
<id>.png.partial
<id>.receipt.partial
<id>.receipt.json
```

Every created state file is `andris:andris 0600`.

The lock serializes ingestion operations. A leftover partial file is not cleaned automatically; it causes STOP and requires explicit recovery authority.

## Atomic inbox publication

The image is downloaded completely under `state/drive-ingest/`, then size and SHA-256 are checked.

Only after integrity passes may the operator publish:

```text
/srv/coloring-pages-content/inbox/<id>.png
```

The state directory and inbox must be on the same filesystem.

The reviewed move first compares the source and destination parent `st_dev` values and fails unless they are on the same filesystem. It then uses GNU `mv` with:

```text
--no-target-directory
--no-clobber
```

This keeps the publish path compatible with the RPi5 host's GNU Coreutils 9.1, where `mv --no-copy` is not available. GNU added `mv --no-copy` in Coreutils 9.2; the existing same-filesystem `st_dev` proof provides the required cross-filesystem fail-closed boundary before `mv` is invoked. The operator also verifies that the staging source disappeared and the destination is a regular non-symlink file, so a silent no-clobber skip is treated as failure.

## Existing importer remains authoritative

The Drive operator does not reimplement image validation or derivative generation.

It requires the installed importer:

```text
/usr/local/bin/coloring-pages-import
root:root 0755
Git blob d07c5a38eb9920b9209dc5719918a6a4cc938305
```

Then it passes the already validated metadata as an argv array to that reviewed importer.

The importer remains responsible for:

- PNG/media validation;
- preserving the original source;
- generating lossless WebP browse derivatives;
- generating the A4 PDF;
- atomically updating `catalog.json`;
- its immutable image and Docker isolation contract.

No image pull or application redeploy is performed by the Drive operator.

## Post-import proof

Before a PASS receipt is recorded, the operator verifies:

- canonical original source size and SHA-256;
- public source size and SHA-256;
- exactly one matching catalogue record;
- exact catalogue metadata and derivative paths;
- non-empty `thumb.webp`, `preview.webp` and `print.pdf`;
- HTTP 200 from the public catalogue, thumbnail, preview, source PNG and PDF URLs.

Public origin is fixed to:

```text
https://coloring.rozkalns.net
```

## Receipt and idempotency

Successful receipt:

```text
/srv/coloring-pages-content/state/drive-ingest/<id>.receipt.json
```

Schema:

```text
rozkalns.rpi5-main.coloring-pages-drive-ingest-receipt.v1
```

A later invocation with the same ID/SHA/size and a matching PASS receipt performs read-only production/public verification and returns `ALREADY_PROCESSED`.

An existing inbox/original/media/catalog ID without a matching success receipt is a STOP.

No overwrite, automatic retry, rollback or failure cleanup is authorized.

## Installer

Tracked installer:

```text
scripts/install-coloring-pages-drive-ingest-operator-v1.sh
```

It requires:

- exact authorized `RPi5_main` SHA;
- clean `main` checkout;
- tracked source identity.

It may install only:

- `/usr/local/bin/coloring-pages-drive-ingest` as `root:root 0755`;
- the bounded state directory when absent;
- the bounded lock file when absent.

It does not:

- read or modify rclone configuration;
- modify OAuth credentials or client IDs;
- change sudoers;
- execute rclone;
- import content;
- change Docker/systemd/network/Cloudflare state.

## OAuth client-id follow-up

The live integrity canary emitted rclone's warning that the shared Google Drive client ID is being retired during 2026.

This source change deliberately does not inspect or modify OAuth credentials. Moving the existing `gdrive:` remote to a dedicated Google OAuth client ID is a separate settings/credentials owner gate and should be completed before unattended ingestion is treated as durable.

## Failure semantics

Before the first mutation, any failed preflight exits without local content changes.

After the operator creates the first staging file, any later error leaves current evidence in place and exits FAIL. It does not retry, roll back, delete partials, overwrite a page ID or choose another transport path.

## Authority boundary

Source merge grants no LIVE authority.

Separate explicit owner authorization is required for:

- installing the operator/state scaffold;
- running Drive read + production content import for exact ID/SHA/size;
- Drive archive/delete operations;
- rclone OAuth client ID or credential changes;
- unrelated deploy, Docker/systemd/network/Cloudflare/permissions mutations.
