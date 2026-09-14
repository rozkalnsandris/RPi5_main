# Control Phase 5 existing credential public-identity reconciliation source

Issue #530 adds a source-only follow-up for the fixed Phase 5 observation credential when the no-overwrite bootstrap correctly reports `TARGET_EXISTS`.

The bootstrap contract remains unchanged: it never overwrites, rotates, deletes or adopts an existing target. Reconciliation is a separate capability with a separate later LIVE gate.

## Fixed boundary

The production entrypoint is `ops/bin/rpi5-control-phase5-observation-credential-reconcile`. It accepts only `--approved-source-sha` and is fixed to the existing Phase 5 repository identity, target, key id and `/usr/bin/openssl` defined by the bootstrap source.

The reconciliation path requires exact Git provenance and a clean tracked tree, root execution, a safe root-owned `/etc/credstore`, absent fixed staging state, and an existing final target that is one regular `root:root` `0600` inode with one hard link and bounded size.

The target is opened read-only with `O_NOFOLLOW`. No create, truncate, write, chmod, chown, rename, unlink, backup, rotation or cleanup operation exists in this path.

## Public identity derivation

OpenSSL documents `pkey -check` as a key-pair consistency check and `pkey -pubout` as restricting encoded output to public components. The source therefore:

1. checks the already-open fixed target with `/usr/bin/openssl pkey ... -check -noout`, discarding stdout and stderr;
2. rewinds the same file descriptor and derives only public DER with `-pubout -outform DER`;
3. requires the exact Ed25519 SubjectPublicKeyInfo prefix and exactly 32 raw public-key bytes;
4. revalidates both the open file descriptor and the fixed path inode/metadata after derivation;
5. emits only the public `keyId`, unpadded base64url raw public key, fixed target classification, contract/status and `mutation_started=false` / `authorization_consumed=false`.

Arbitrary OpenSSL diagnostics, PEM text, protected directory contents and credential file bytes are never included in receipts.

References:
- https://docs.openssl.org/3.0/man1/openssl-pkey/
- https://docs.openssl.org/1.1.1/man7/Ed25519/

## Authorization boundary

This merged source alone does not authorize reading the production target. A later explicit RPi5 LIVE authorization must bind one exact merged `RPi5_main` SHA before the root reconciliation entrypoint is executed.

A successful public-identity receipt still does not authorize Control secret/binding mutation, signed delivery, systemd/service changes or any other runtime mutation. Those remain separate owner gates.
