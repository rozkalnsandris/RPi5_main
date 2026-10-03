# Coloring Pages importer operator v1

Issue: `#858`

## Purpose

Provide one trusted RPi5 command for publishing a reviewed coloring-page PNG without installing Python/Pillow on the host and without allowing the consumer repository to choose arbitrary Docker, host-path or image identities.

The production command is intended to be:

```bash
coloring-pages-import /srv/coloring-pages-content/inbox/fire-pup-001.png
```

Source merge does not install or execute this command.

## Frozen consumer identity

- repository: `rozkalnsandris/coloring-pages`
- source: `ab8f874f681fb2adb6f18f4a7c8066b44ace443b`
- immutable image: `ghcr.io/rozkalnsandris/coloring-pages@sha256:5f61560cb674224052bc3ab8ca086c7997930027459f6c2648714d12c60af796`
- image entrypoint: `/usr/local/bin/coloring-pages-import`

The wrapper never uses `:production`, `:latest` or another mutable tag. It also uses `--pull=never`, so a normal content import cannot change the image cache or resolve a new remote image.

## Host operator

Tracked source:

```text
ops/bin/coloring-pages-import
```

Reviewed installed identity:

```text
/usr/local/bin/coloring-pages-import
root:root 0755
```

The installed file is root-owned to protect the reviewed command contract, but execution is allowed only as host user `andris`. Root execution fails closed. The Docker container itself runs as the caller UID:GID so produced content remains owned by the content-store operator.

## Content boundary

The wrapper requires the existing bootstrap layout and exact top-level metadata:

```text
/srv/coloring-pages-content/            andris:andris 0755
├── inbox/                              andris:andris 0755
├── originals/                          andris:andris 0755
├── public/                             andris:andris 0755
│   ├── catalog.json                    andris:andris 0644
│   └── media/                          andris:andris 0755
└── state/                              andris:andris 0755
```

The source must be a regular non-symlink `.png` whose resolved parent is exactly:

```text
/srv/coloring-pages-content/inbox
```

Nested paths and sources outside the inbox are rejected before Docker starts.

The wrapper allows only these optional metadata arguments:

- `--id`
- `--title`
- `--character`
- `--category`
- `--age`
- `--difficulty`
- `--language`

`--content-root` and any other argv are rejected by the host wrapper.

## Docker isolation

The exact one-off invocation is constrained to:

- `--rm`
- `--pull=never`
- `--network none`
- read-only container root
- `/tmp` tmpfs with `noexec,nosuid,nodev`
- `--cap-drop ALL`
- `--security-opt no-new-privileges:true`
- current host operator UID:GID
- exactly one host bind: `/srv/coloring-pages-content` to the identical container path, read-write
- fixed entrypoint `/usr/local/bin/coloring-pages-import`

The read-write bind is necessary because one successful import writes canonical originals, generated derivatives and an atomically replaced catalogue. The long-running nginx service remains separate and sees only `public/` read-only.

## Installer

Tracked installer:

```text
scripts/install-coloring-pages-importer-operator-v1.sh
```

The installer:

- requires explicit `--expected-rpi5-main-sha`;
- requires an exact clean `main` checkout at that SHA;
- performs no `git fetch`;
- installs only the reviewed wrapper to `/usr/local/bin/coloring-pages-import`;
- verifies root ownership, mode and exact Git blob identity after installation;
- does not run/pull Docker;
- does not import or change content;
- does not touch systemd, Cloudflare, networking, secrets or permissions outside the operator file.

A later LIVE authorization must separately cover any checkout reconciliation plus the installer mutation.

## Runtime sequencing

The safe sequence is:

```text
source merge
→ exact-main CI
→ separate LIVE operator installation
→ ensure exact immutable image is locally available through reviewed app deployment/pull authority
→ separate production import command
```

If the immutable image is absent locally, `--pull=never` makes the import fail instead of silently fetching another image.

## Failure semantics

The wrapper validates host/content/image arguments before `docker run`. Once Docker starts, production import mutation has begun. Any failure or ambiguity after that point must be treated according to the current owner authorization; no automatic retry, rollback, cleanup or alternate image is implied by this source contract.

## Authority boundary

Source merge grants no LIVE authority.

Separate owner authorization is required for:

- installing or replacing the host wrapper;
- reconciling the RPi5 checkout used by the installer;
- pulling/deploying the immutable image;
- running an import against production content;
- any Docker/systemd/network/Cloudflare/secret/permission mutation outside the exact reviewed envelope.
