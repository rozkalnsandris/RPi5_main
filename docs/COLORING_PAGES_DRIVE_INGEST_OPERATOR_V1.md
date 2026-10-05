# Coloring Pages publish operator v1 — single-page + multi-page

## Purpose

Provide one bounded RPi5 command for the approved content path:

```text
Drive pending PNG page(s) + manifest
  -> verify owner-bound ID / per-page SHA-256 / size / metadata
  -> verify every page before the first inbox publication
  -> publish ordered PNG page(s) to the content inbox
  -> run the immutable Coloring Pages importer image once
  -> verify catalog/media/public URLs
  -> write one success receipt
```

There is no second installed importer wrapper in this design.

Tracked source:

```text
ops/bin/coloring-pages-drive-ingest
```

Installed command:

```text
/usr/local/bin/coloring-pages-drive-ingest
```

Source merge does not install or execute the operator. The same installed command remains backward-compatible with the production v1 single-page manifest and adds the reviewed v2 multi-page manifest; there is no second publish operator.

## Fixed Drive boundary

The operator has no caller-selectable remote, folder or filename.

Reviewed values:

```text
remote          gdrive:
root folder id  1F0pxqoRgtZl7JQVcyvYVZxKvx6eOnytn
queue path      pending/
config          <owner-home>/.config/rclone/rclone.conf
config metadata root:andris 0600
```

The operator is read-only toward Drive. It uses normal non-`--fast-list` discovery and `rclone cat`; it never uploads, moves, archives or deletes Drive objects and never reads or prints the rclone configuration contents.

## Invocation

Single-page v1 remains unchanged:

```bash
coloring-pages-drive-ingest \
  --id <page-id> \
  --expected-sha256 <64-lowercase-hex> \
  --expected-size <bytes>
```

Multi-page v2 binds every page explicitly:

```bash
coloring-pages-drive-ingest \
  --id <activity-id> \
  --expected-page 1:<sha256>:<bytes> \
  --expected-page 2:<sha256>:<bytes>
```

v2 accepts 2–12 pages. Page indexes must be contiguous and ordered from 1. Drive filenames are fixed as `pending/<id>-<index>.png`; the single `pending/<id>.json` manifest is still the readiness signal. The operator lists the exact expected filenames, validates the complete v2 manifest against the owner-bound page identities, downloads and verifies every page, and only then begins inbox publication.

Unknown manifest/page fields are rejected. Category is checked against the current reviewed Coloring Pages category set before any PNG is published into the inbox.

## Local staging and no-overwrite

The operator runs as `andris`, uses one lock, creates staging files as `andris:andris 0600`, and never overwrites an existing page ID.

The downloaded PNG is checked for exact byte size and SHA-256 before it is moved into:

```text
/srv/coloring-pages-content/inbox/<id>.png
```

The state directory and inbox must share one filesystem. Publication uses GNU `mv --no-target-directory --no-clobber` after a same-filesystem check.

Leftover partial state is preserved and causes STOP. There is no automatic retry, cleanup, rollback or overwrite.

## Immutable importer image

The same publish operator directly runs the reviewed immutable image:

```text
ghcr.io/rozkalnsandris/coloring-pages@sha256:ebb52f87849d02b2ba467b5525c37b09864921530d1af11a80424208659bf868
```

Entrypoint:

```text
/usr/local/bin/coloring-pages-import
```

The container is run with:

- `--pull=never`;
- `--network none`;
- read-only container root filesystem;
- `--cap-drop ALL`;
- `no-new-privileges`;
- the operator user's UID/GID;
- one RW bind of `/srv/coloring-pages-content`;
- a bounded tmpfs for `/tmp`.

The importer image remains responsible for PNG/media validation, preserving exact source bytes, generating browse derivatives and the cleaned print PNG, and updating `catalog.json`.

The host does **not** require a separate `/usr/local/bin/coloring-pages-import` wrapper.

## Post-import proof

Before writing a PASS receipt, the operator verifies:

- canonical private original source size and SHA-256;
- exactly one catalog entry whose reviewed core fields match exactly;
- non-empty `thumb.webp` and `preview.webp`;
- HTTP 200 for catalog, thumbnail and preview.

For the current private-master media contract, `public/media/<id>/source.png` is absent, a non-empty `print.png` must exist, the catalog `print` field must point to that PNG, and its public URL must return HTTP 200. Additive legacy-only catalog fields are tolerated so already-published records remain verifiable, but every reviewed core field must still match exactly.

During the bounded transition, the operator also accepts the legacy layout. If `public/media/<id>/source.png` exists, it must still match the approved source size/SHA-256, the catalog `print` field must point to that legacy source, and its public URL must return HTTP 200. This allows the verifier to be installed before the importer image is repinned without breaking existing content publication.

Public origin is fixed to:

```text
https://coloring.rozkalns.net
```

Successful state is recorded at:

```text
/srv/coloring-pages-content/state/drive-ingest/<id>.receipt.json
```

A matching success receipt allows read-only re-verification and returns `ALREADY_PROCESSED`.

## Installer

The single installer remains:

```text
scripts/install-coloring-pages-drive-ingest-operator-v1.sh
```

It may install only the publish operator plus its bounded state directory and lock. It does not run rclone, Docker, import content, change credentials, change sudoers, or alter systemd/network state.

## Authority boundary

Source merge grants no LIVE authority.

Separate explicit owner authorization is required to install/update the host operator and to execute a production content publish. Drive archive/delete, credential changes, Cloudflare/network changes and unrelated host mutations remain outside this path.

References:

- https://rclone.org/commands/rclone_cat/
- https://rclone.org/drive/
- https://www.gnu.org/software/coreutils/manual/html_node/mv-invocation.html


## Multi-page v2 post-import proof

For a v2 activity the operator requires private originals `source-1.png` through `source-N.png` to match every owner-bound size/SHA-256. It verifies one catalogue item whose top-level `preview`/`print` point to page 1 and whose ordered `pages[]` exactly matches `preview-N.webp` + `print-N.png`. `thumb.webp`, every page derivative and every public URL must pass before the v2 PASS receipt is written.

The operator invokes the importer once with all ordered direct-child inbox paths and an explicit activity ID. It expects the immutable importer result `IMPORTED=<id> PAGES=<N>`. A failure after persistent mutation starts is a STOP; no automatic retry, rollback or cleanup is added.
