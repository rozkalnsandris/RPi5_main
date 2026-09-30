# Balkons bot production deployment and rollback contract

Issue: `RPi5_main#192`

Status: **source-only design; no production authorization**.

## Current decision: encrypted systemd credentials

The historical plaintext `/etc/credstore/balkons-bot-*` contract is superseded.
The reviewed target uses systemd encrypted credentials so the long-lived host files
contain ciphertext only.

The service receives exactly five credential IDs through its private
`$CREDENTIALS_DIRECTORY`:

- `telegram-token`
- `telegram-chat-id`
- `mqtt-host`
- `mqtt-username`
- `mqtt-secret`

The corresponding ciphertext objects are fixed at:

- `/etc/credstore.encrypted/balkons-bot-telegram-token`
- `/etc/credstore.encrypted/balkons-bot-telegram-chat-id`
- `/etc/credstore.encrypted/balkons-bot-mqtt-host`
- `/etc/credstore.encrypted/balkons-bot-mqtt-username`
- `/etc/credstore.encrypted/balkons-bot-mqtt-secret`

`ops/systemd/balkons-bot-runtime-override.conf` clears both the plaintext and
encrypted credential lists, then adds exactly these five
`LoadCredentialEncrypted=ID:PATH` mappings. No non-empty `LoadCredential=` mapping
is allowed.

The application source remains unchanged: it reads only the five IDs from
`$CREDENTIALS_DIRECTORY`; it does not know or read the ciphertext paths.

## Why this matches Debian/systemd 252

Debian 12's systemd 252 supports `LoadCredentialEncrypted=` and
`systemd-creds encrypt`. The encrypted object is authenticated/decrypted by systemd
when the service is started and is then exposed under the service credential
directory. The reviewed provisioning form binds each encrypted object to its exact
credential ID:

```text
/usr/bin/systemd-creds encrypt --with-key=host --name=<ID> - <OUTPUT_PATH>
```

The explicit `--name=<ID>` is required even though the output filename is stable;
it makes credential-purpose binding reviewable and prevents silent repurposing.
`--with-key=host` binds encryption to the systemd host credential key. Ciphertext
objects and the host credential key are never committed to Git.

## Owner-run provisioning boundary

Provisioning is a **separate owner-run secret operation**. It is not performed by
this repository source change and must not be performed by an agent that would need
to read existing plaintext credentials.

For each of the five IDs, the owner-run flow is:

1. ensure `/etc/credstore.encrypted` exists as a real root-owned directory and is
   not group/world writable;
2. supply the plaintext credential to standard input from a trusted local source;
   never place it in argv, shell history, Git, chat, a temporary plaintext file or
   logs;
3. execute the fixed systemd 252 command form above with the matching ID and fixed
   output path;
4. leave only the encrypted output on disk;
5. set the encrypted object to root ownership, mode `0400`, regular-file type and
   one hard link;
6. do not run `systemd-creds decrypt` as part of normal provisioning or verification.

Example command shape, with the value supplied privately on standard input:

```text
sudo /usr/bin/systemd-creds encrypt --with-key=host --name=telegram-token - /etc/credstore.encrypted/balkons-bot-telegram-token
```

Repeat only with the matching reviewed ID/path pair. The command examples contain
no credential values.

## Metadata-only credential preflight

Tracked `ops/bin/balkons-bot-preflight` validates ciphertext **metadata only**. It
does not open or hash any credential object.

Every fixed encrypted object must be:

- present at the exact reviewed path;
- a regular file with link count 1, never a symlink;
- owned by root;
- mode `0400`;
- non-empty and no larger than 65536 bytes.

The public-safe report contains only fixed public IDs, counts/booleans and blocker
codes. It records `content_read=false` and `content_hashed=false`. Missing or
metadata-drifted objects block deployment before mutation.

## Additive source/service deployment

The later deployment remains limited to two public reviewable files:

1. `/usr/local/lib/rpi5-balkons-bot.py`
   - exact bytes of tracked `ops/lib/balkons-bot.py`;
   - regular one-link root-owned file, mode `0644`.
2. `/etc/systemd/system/balkons-bot.service.d/95-rpi5-source-credentials.conf`
   - exact bytes of tracked `ops/systemd/balkons-bot-runtime-override.conf`;
   - regular one-link root-owned file, mode `0644`.

The existing K10 `90-rpi5-no-sigkill.conf` remains untouched. The overlay preserves
the existing private service identity and lifecycle values, clears historical
command/environment credential surfaces, keeps `SendSIGKILL=no`, and applies the
reviewed hardening directives.

No source merge authorizes installation, credential provisioning, `daemon-reload`,
service restart, MQTT/broker changes, Home Assistant/ESP32 changes or a pump command.

## Read-only deployment verifier

Tracked artifact: `ops/bin/balkons-bot-deploy-verifier`.

The verifier remains non-root and read-only. It binds the exact Git SHA and
verifier/source/overlay/preflight hashes, checks the public overlay contract, calls
the preflight, and accepts the credential prerequisite only when all five encrypted
objects have valid metadata with `content_read=false` and `content_hashed=false`.

### `--check`

Before any deployment mutation it requires:

- exact reviewed repository SHA on branch `main`;
- clean/tracked verifier, source, overlay and preflight paths;
- exact K10 drop-in baseline;
- both forward deployment targets absent;
- current service/source baseline still accepted;
- all five encrypted ciphertext objects metadata-valid;
- exact overlay containing no plaintext `LoadCredential=` mapping and exactly five
  reviewed `LoadCredentialEncrypted=` mappings.

Success returns `READY` with no mutation and no credential-content access.

### `--verify`

After a separately authorized deployment/restart it additionally requires:

- exact deployed source/overlay hashes and metadata;
- the deployed overlay still satisfies the encrypted-credential contract;
- complete preflight PASS;
- stable `MainPID` during the bounded argv check;
- process argv exactly `/usr/bin/python3` and
  `/usr/local/lib/rpi5-balkons-bot.py`.

Raw argv is never emitted and process environments are never read.

## Future LIVE sequence

Only after this source revision is merged and exact-main CI passes may a later,
separately explicit owner LIVE decision consider production work. The intended
ordering is:

1. fresh exact-source and host metadata preflight;
2. owner-run encrypted credential provisioning if the five ciphertext objects are
   not already ready;
3. re-run metadata-only preflight and require PASS;
4. exact non-root deployment verifier `--check`;
5. exact bounded installation of the two reviewed public files;
6. one `systemctl daemon-reload` and one `systemctl restart balkons-bot.service` if
   explicitly authorized;
7. deployment verifier `--verify` and service-health confirmation.

Credential provisioning and service mutation are distinct sensitive classes. An
authorization must explicitly include the class it permits. Authorization is
consumed at the first authorized mutation; later error or ambiguity means evidence
plus STOP, with no undeclared retry/cleanup/rollback/alternate path.

## Rollback

Rollback remains a separate owner decision. A reviewed rollback may remove only the
exact #192 source/overlay deployment files, perform the explicitly authorized
systemd lifecycle actions, and prove the historical service baseline again.

Rollback must **not** delete, replace, decrypt, rotate or otherwise mutate the five
encrypted credential objects unless a separate credential rollback/rotation action
is explicitly authorized. It must not alter broker, HA, ESP32, network, packages,
Docker, data or pump state.

## Remaining scope boundary

This revision only moves the balkons-bot runtime credential transport from
long-lived plaintext files to host-bound encrypted systemd credential objects while
keeping application behavior unchanged.

Legacy shared MQTT credential rotation/revocation remains `RPi5_main#189`; this
source revision does not perform that migration.
