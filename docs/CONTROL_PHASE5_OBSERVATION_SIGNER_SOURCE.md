# Control Phase 5 RPi5 observation signer source contract

This document defines the source-only signer and key-lifecycle boundary for the
Phase 5 RPi5 production-visibility observation transport. It does not provision a
production key and does not activate runtime delivery.

The existing transport remains authoritative for payload serialization, signing
bytes, delivery metadata and Control provenance. The signer added by #444 only
turns those already-validated signing bytes into an Ed25519 signature.

## Reproducible signing capability

The signer invokes the fixed host capability `/usr/bin/openssl`; it does not use
`PATH` lookup and does not depend on the host user's Python `cryptography` install.
Ed25519 signing uses OpenSSL `pkeyutl -sign -rawin` in one-shot mode.

Because OpenSSL 3 Ed25519 one-shot signing requires an input with a known size,
the exact transport signing bytes are copied to a Linux `memfd` and passed to
OpenSSL through `/proc/self/fd/<fd>`. The signing payload is not written to a
persistent file by the signer adapter.

## Protected credential boundary

Production private key material is accepted only through systemd's
`$CREDENTIALS_DIRECTORY`. The fixed credential basename is:

`control-phase5-observation-ed25519.pem`

The adapter requires an absolute, non-symlink-resolved credential directory with
no group/other permissions. It opens the credential with `O_NOFOLLOW`, requires a
regular non-empty file with no group/other permissions, and never reads private
key bytes into Python. OpenSSL receives only the already-open credential FD.

The accepted source contract is an unencrypted PEM private key that OpenSSL can
parse as Ed25519. Malformed input, another key type, an ambiguous/symlink source,
an insecure permission mode, a missing credential or unsupported host capability
fails closed with a public-safe error code. OpenSSL stderr is never surfaced by
the adapter.

The signer caches the derived public key at load time and re-derives it from the
same opened credential FD before every sign or receipt operation. An unexpected
credential replacement therefore fails with `CREDENTIAL_CHANGED`; rotation must
be an explicit lifecycle action that reloads the signer.

## Key identity and public verification receipt

`keyId` is operator-selected and must match Control exactly:

`^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`

The signer is bound to one `keyId` and refuses to sign transport bytes carrying a
different key ID or a different signing domain/version. This prevents the Phase 5
credential from becoming a generic signing oracle.

The only exportable key material is the raw 32-byte Ed25519 public key. The
public-safe receipt shape is:

```json
{"keyId":"rpi5-prod-YYYY-MM","publicKeyBase64url":"<unpadded-base64url-32-byte-public-key>"}
```

`publicKeyBase64url` is exactly 43 unpadded base64url characters. Private key bytes,
credential contents and OpenSSL diagnostics are never part of the receipt.

## Lifecycle gates

1. Source readiness: merge the reviewed signer/docs/tests only after normal CI and
   explicit MERGE authorization. This creates no production credential.
2. Production key generation/provisioning: a separate STRICT/LIVE authorization
   must name the exact RPi5 credential target and generation/provisioning method.
3. Public-key handoff: reading the production credential to derive this receipt is
   protected-runtime access and requires the same separately authorized lifecycle
   step. Only the public receipt may leave RPi5.
4. Control verification-key provisioning: adding the corresponding verification
   key to `CONTROL_RPI5_OBSERVATION_VERIFICATION_KEYS` is a separate Control LIVE
   mutation. The private key must never be sent to Control.
5. Runtime signer/transport activation is another explicit LIVE gate after both
   sides are provisioned and their exact source/runtime baselines are revalidated.

Key rotation follows the same order with a new operator-selected `keyId`. The old
and new verification-key overlap/removal policy belongs to the separately reviewed
Control provisioning/cutover plan, not to this source-only adapter.

## Non-authority

This source change does not generate a real production key, write any protected
credential path, install or upgrade OpenSSL, modify systemd units, read existing
production credentials, call Control, mutate Worker/D1/Queue state, or activate
RPi5 observation delivery. Source merge is not LIVE authorization.

Tests create only temporary fixture private keys inside test-owned directories,
exercise the existing exact transport signing bytes, reconstruct the public
Ed25519 SPKI from the exported raw key, and verify the produced signature with
OpenSSL. No fixture private key is committed.
