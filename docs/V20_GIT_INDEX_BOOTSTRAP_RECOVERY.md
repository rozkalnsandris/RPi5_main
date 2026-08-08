# V20 Git index bootstrap recovery

## Purpose

This recovery exists for one narrow failure mode: a privileged repository inspection has left the primary checkout's `.git/index` owned by root, so the normal checkout owner cannot read or update the index and therefore cannot fast-forward to the already-reviewed recovery code.

The bootstrap helper is designed to be fetched from an exact GitHub commit into a temporary directory and invoked through `sudo` with an explicit checkout path. It performs no Git operation.

## Why this shape

Git documents that `git status` refreshes and may write the index by default. Read-only automation should therefore use `git --no-optional-locks status` or `GIT_OPTIONAL_LOCKS=0` after ownership has been restored. The bootstrap helper itself avoids Git entirely because it must work before the normal user can access the index.

The ownership repair is deliberately one-file only. It rejects symlinks and a live `index.lock`, requires the checkout and `.git` directory to belong to the `sudo` caller, requires the checkout to be on `main`, accepts only an index already owned by the checkout owner or by root, and uses a conditional non-dereferencing `chown --from` operation on exactly `.git/index`.

Before changing ownership it records the index SHA-256, mode, and size as root. After changing ownership it requires all three values to remain identical.

## Boundaries

The helper does not fetch, merge, reset, push, rebase, run a service lifecycle command, invoke Docker, mutate Cloudflare, generate application content, or touch a database. It never performs a recursive ownership change.

After bootstrap recovery passes, the normal checkout owner performs the exact-SHA fast-forward. Privileged V20 verification then uses the separately reviewed safe retry path where Git inspection is de-privileged and optional index locks are disabled.

Merging this recovery changes source only and performs no production mutation.
