# Control Phase 5 observation credential bootstrap source

Issue #510 adds the source-only contract for a later separately authorized creation of the RPi5 Phase 5 Ed25519 observation-signing credential. This source does not create, inspect, rotate, install or activate any production credential by itself.

## Fixed production contract

The production entrypoint is `ops/bin/rpi5-control-phase5-observation-credential-bootstrap`.

Its production boundary is fixed in source:

- repository: `rozkalnsandris/RPi5_main`;
- credential directory: `/etc/credstore`;
- final credential: `/etc/credstore/control-phase5-observation-ed25519.pem`;
- public key id: `rpi5-prod-2026-09`;
- algorithm: Ed25519 only;
- generator: `/usr/bin/openssl` only;
- Git executable: `/usr/bin/git` only;
- final owner/group: `root:root`;
- final mode: `0600`.

The CLI accepts only one mode (`--preflight` or `--apply`) and one exact reviewed source identity (`--approved-source-sha`). There is no caller-selected directory, filename, key id, algorithm, OpenSSL path, command, shell, argv, environment or alternate target.

The existing runtime signer remains unchanged: systemd delivers this credential through its private `$CREDENTIALS_DIRECTORY`, and `control_phase5_observation_signer.py` opens only `control-phase5-observation-ed25519.pem` inside that private directory.

## Preflight-only mode

`--preflight` is intentionally non-mutating. It requires all of the following before returning `PREFLIGHT_PASS`:

1. the required Linux no-follow/dir-fd link/stat/unlink capabilities and `/proc/self/fd` are available;
2. execution is from the exact Git worktree root embedded by the source module;
3. fixed `/usr/bin/git` is a root-owned regular executable and is not group/world writable; every Git provenance invocation uses only command-scoped `-c safe.directory=<exact resolved worktree root>` so a root preflight can validate the owner-created trusted checkout without widening root global/system Git trust or inheriting `SUDO_UID`;
4. Git `origin` identifies `rozkalnsandris/RPi5_main` using one of the fixed canonical URL forms;
5. current `HEAD` equals the supplied 40-character lowercase `--approved-source-sha`;
6. tracked worktree state is clean;
7. the effective user is root for the production wrapper;
8. `/usr/bin/openssl` is a root-owned regular executable, is not group/world writable and advertises Ed25519 support;
9. `/etc/credstore` already exists as a real non-symlink directory, is owned by root and is not group/world writable;
10. neither the exact final credential nor the fixed staging name exists, including as a symlink.

Preflight does not create a file and does not open/read a production private key. Its receipt always has `mutation_started=false` and `authorization_consumed=false`.

## Atomic no-overwrite creation

`--apply` is source capability only until a later explicit RPi5 STRICT/LIVE authorization permits exactly this mutation.

The apply path repeats all preconditions immediately before mutation. The first filesystem creation is an `O_CREAT|O_EXCL|O_NOFOLLOW` open of the fixed staging name inside the already-open trusted credential directory. Only after that call succeeds are both state flags set:

- `mutation_started=true`;
- `authorization_consumed=true`.

The staging inode is forced to `root:root` / `0600`. `/usr/bin/openssl genpkey -algorithm ED25519` writes PEM bytes directly to that file descriptor; private PEM bytes are never captured in Python output or an in-memory subprocess pipe, and OpenSSL stderr is discarded.

Before publication, source validates that the staging object is one bounded regular `0600` file with the expected ownership and derives only the 32-byte raw Ed25519 public key. Publication uses a same-directory hard link to the exact final name. Link creation fails rather than replacing any existing final object. The source proves that final and staging names reference the same inode, then removes the staging name as part of the successful transaction and revalidates the one-link final object.

There is no exception cleanup path. If any error occurs after the first staging creation, the operation returns/raises fail-closed state with authorization consumed and leaves the observable filesystem state untouched for later owner-reviewed reconciliation. No automatic retry, rollback, deletion, alternate staging target, overwrite, rotation or cleanup is permitted.

A pre-existing staging object likewise fails closed before a new mutation and is never removed automatically.

## Public-safe receipts

The source emits only the fixed public-safe receipt surface:

- `contract`;
- `status`;
- public `keyId`;
- `publicKeyBase64url` (`null` for preflight/failure, otherwise exactly the raw 32-byte Ed25519 public key encoded as unpadded base64url);
- `targetClass`;
- `mutation_started`;
- `authorization_consumed`;
- stable public error code on failure.

Receipts do not contain private-key bytes, PEM text, temporary or protected filesystem paths, OpenSSL stderr, command output, protected directory contents or arbitrary exception text.

## Source provenance and failure semantics

A first owner-run root preflight against the trusted detached Phase 5 checkout failed closed before credential mutation with `SOURCE_PROVENANCE_INVALID`, `mutation_started=false` and `authorization_consumed=false`. The checkout was clean, exact-SHA and canonical-origin, but it was owned by the operator account while the bootstrap intentionally replaced the subprocess environment with only `LC_ALL=C`. That removed Git's `SUDO_UID` ownership exception and exposed the same root-side ownership class previously repaired in the repository's broker installer. The bounded repair is command-scoped exact `safe.directory`; wildcard trust, root global/system Git configuration, environment widening and credential-surface changes remain forbidden.

The later LIVE authorization must bind one exact merged `RPi5_main` SHA. Both preflight and apply require the supplied SHA to equal current `HEAD` and require the fixed repository identity. No reset, rebase, clean, checkout rewrite, force push or source-repair behavior exists in this operator.

Any mismatch or ambiguous filesystem/source state fails before mutation. After the first staging creation, any error is terminal for that authorization: preserve only public-safe evidence and STOP. A new owner decision is required before any retry, rollback, cleanup or alternate action.

## Ordered later LIVE sequence

Source merge does not authorize any step below. After this change is merged and exact-main CI is green, the intended sequence is:

1. run fresh read-only source/runtime preflight against the exact merged RPi5 SHA;
2. STOP for a separate RPi5 STRICT/LIVE authorization to execute exactly one credential creation and return only the public receipt;
3. using only that public key receipt, STOP for a separate Control LIVE authorization to reconcile/provision `CONTROL_RPI5_OBSERVATION_VERIFICATION_KEYS` for `rpi5-prod-2026-09`;
4. obtain fresh Control GET-only post-activation evidence and a fresh `PHASE5_RPI5_SIGNER_HANDOFF_V1` bound to the reconciled public key identity;
5. run the already-merged Phase 5 delivery source `--validate-only` path with fresh sanitized observation input;
6. STOP for a separate RPi5 runtime/delivery LIVE authorization before any signed production observation is sent;
7. after one authorized delivery, reconcile the Control side read-only.

These are distinct trust/owner gates. Credential creation does not authorize Control secret mutation, and Control reconciliation does not authorize RPi5 runtime delivery.
