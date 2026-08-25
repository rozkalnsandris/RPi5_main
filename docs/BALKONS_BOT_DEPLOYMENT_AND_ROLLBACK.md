# Balkons bot production deployment and rollback contract

Issue: `RPi5_main#192`

Status: **source-only deployment design; no production authorization**.

## Purpose

Phase K10 removed the effective-systemd lifecycle blocker and proved the current
`balkons-bot.service` baseline is loaded, active/running, non-root, still executing
the reviewed H3 historical live source, and effective `SendSIGKILL=no` without a
service restart.

This document defines the next source-only layer: an exact additive deployment of
the reviewed secret-free bot source and its systemd credential references. Nothing
in this document authorizes a host write, credential read/change, service restart,
MQTT operation, broker change, Home Assistant change, ESP32 change, or pump command.

## Design boundary

The deployment deliberately does **not** replace, copy, or read the raw live base
unit, and it does not copy the historical secret-bearing live Python source.
Repository rules forbid using raw production configuration or secret-bearing bytes
as deployment/rollback material.

Instead, the forward change is additive and limited to two public, reviewable files:

1. `/usr/local/lib/rpi5-balkons-bot.py`
   - exact bytes of tracked `ops/lib/balkons-bot.py`;
   - regular, non-symlink, root-owned, mode `0644`.
2. `/etc/systemd/system/balkons-bot.service.d/95-rpi5-source-credentials.conf`
   - exact bytes of tracked `ops/systemd/balkons-bot-runtime-override.conf`;
   - regular, non-symlink, root-owned, mode `0644`.

The existing base unit, historical live source, and K10
`90-rpi5-no-sigkill.conf` remain untouched. This makes rollback removal-only for
the two new exact files instead of requiring a raw systemd/source backup.

## Runtime overlay

The reviewed overlay uses systemd list-reset semantics to replace only the runtime
command and credential list while preserving private service identity and the
already-proven lifecycle values from the base unit:

- reset `ExecStart=` and set exactly
  `/usr/bin/python3 /usr/local/lib/rpi5-balkons-bot.py`;
- reset `LoadCredential=` and add exactly the five reviewed credential names;
- keep `SendSIGKILL=no`;
- apply the non-secret service hardening already defined by the tracked source
  template;
- do not set `User=`, `Restart=`, `RestartSec=`, `TimeoutStopSec=`, enablement,
  dependencies, broker settings, or any private identity value.

The five fixed credential source paths are:

- `/etc/credstore/balkons-bot-telegram-token`
- `/etc/credstore/balkons-bot-telegram-chat-id`
- `/etc/credstore/balkons-bot-mqtt-host`
- `/etc/credstore/balkons-bot-mqtt-username`
- `/etc/credstore/balkons-bot-mqtt-secret`

No credential content appears in Git, argv, the overlay, verifier output, or the
rollback manifest.

## Credential prerequisite — metadata only

This workstream does not provision, recover, rotate, or inspect credential values.
Before the first future deployment mutation, a separately owner-authorized STRICT
preflight must inspect only metadata for the five fixed credential files and fail
closed unless every file is:

- present at its exact fixed path;
- a regular non-symlink file;
- owned by root;
- mode `0400` or `0600`;
- non-empty and no larger than 4096 bytes.

The preflight must not open or hash credential contents and must print no path other
than the fixed public contract paths already tracked here. If any credential is
absent or unsafe, deployment stops before its first deployment mutation. Supplying
credential values is a separate owner-managed secret operation and is not implied
by merge or by a generic `turpini`.

The same pre-mutation gate must query effective `LoadCredential` metadata in memory
and accept only an empty current list. It may emit only `EMPTY`/`NONEMPTY`, not raw
entries. This ensures the overlay's explicit `LoadCredential=` reset cannot erase
an unexpected pre-existing credential contract.

## Read-only deployment verifier

Tracked artifact: `ops/bin/balkons-bot-deploy-verifier`.

It is deliberately non-root and read-only. It has only two modes.

### `--check`

Before deployment it requires:

- exact reviewed repository SHA and `main` branch;
- exact trusted checkout fingerprint;
- verifier/source/overlay/preflight paths Git-tracked, clean and exact-SHA256 bound;
- exact K10 `90-rpi5-no-sigkill.conf` root-owned mode-0644 hash;
- both forward deployment targets absent;
- the existing complete production preflight to PASS against the H3 historical
  live-source SHA;
- the K10 service identity/lifecycle hashes and values to remain unchanged.

A successful check returns `READY`, `credential_content_read=false`,
`mutation_started=false`, and `writes_performed=false`.

### `--verify`

After an authorized deployment/restart it additionally requires:

- both forward targets regular non-symlink root-owned mode-0644 and exact hashes;
- the complete production preflight to PASS with the tracked source SHA256 as the
  expected live-source provenance;
- the same service user, fragment, system Python and lifecycle contract as K10;
- stable `MainPID` across one bounded `/proc/<MainPID>/cmdline` read;
- process argv to contain exactly two UTF-8 values:
  `/usr/bin/python3` and `/usr/local/lib/rpi5-balkons-bot.py`.

Raw argv is never printed. No process environment is read.

## Root trust boundary

No repository executable is to be executed or copied as root. A future Composite
STRICT transaction must use only fixed system binaries plus exact reviewed public
bytes/hashes for the privileged segment.

The root segment must not read the tracked checkout through an unverified path.
The non-root verifier first proves exact Git/artifact bindings; root then
materializes only exact already-bound source/overlay bytes and independently
verifies target metadata and SHA256 before `daemon-reload` or restart.

## Root-only rollback manifest

Before the first forward file is created, the future transaction must create and
verify this fixed manifest:

`/var/lib/rpi5-rollback/issue192-balkons-bot-v1.json`

Contract:

- parent directory root-owned mode `0700` if it must be created;
- manifest regular, non-symlink, root-owned mode `0600`;
- contains only public identifiers/hashes and boolean pre-state facts;
- contains no raw source, unit, credentials, private paths or usernames.

At minimum it binds:

- exact repository SHA;
- verifier/source/overlay/preflight/K10-drop-in SHA256 values;
- the two exact forward target paths;
- proof that both forward targets were absent immediately before forward mutation;
- K10 sanitized identity/lifecycle hashes;
- expected H3 historical live-source SHA256.

The manifest is evidence and a rollback authorization input, not automatic rollback.

## Future Composite STRICT forward sequence

After source review and merge, a fresh owner authorization may cover one fail-closed
transaction only if it binds the exact merged SHA, host/checkout fingerprint,
artifact SHA256 values, K10 baseline, fixed targets and explicit exclusions.

The intended sequence is:

1. fresh GitHub/source reconciliation;
2. non-root deployment verifier `--check`;
3. root metadata-only credential readiness and effective-`LoadCredential` empty gate;
4. immediate exact SHA/target-absence revalidation;
5. create and verify the root-only rollback manifest;
6. materialize the exact reviewed source target;
7. materialize the exact reviewed overlay target;
8. verify both target owner/mode/SHA256 values;
9. run exactly one `systemctl daemon-reload`;
10. run exactly one `systemctl restart balkons-bot.service`;
11. run non-root deployment verifier `--verify`.

The authorization is consumed at the first authorized host mutation. Any error,
drift or ambiguity after that point preserves sanitized evidence and STOPs. There
is no automatic retry, cleanup, rollback, alternate path, generic process kill, or
SIGKILL fallback.

## Separately authorized rollback

Rollback is never automatic and requires a fresh owner authorization. It must first
verify the root-only manifest and exact forward file hashes. Root may then:

1. remove only the exact `95-rpi5-source-credentials.conf` target;
2. remove only `/usr/local/lib/rpi5-balkons-bot.py`;
3. run one `systemctl daemon-reload`;
4. run one `systemctl restart balkons-bot.service`;
5. run the already-reviewed K10 verifier `--verify` to prove the historical H3
   source is active again with effective `SendSIGKILL=no`.

Rollback must not alter the five credential files, the K10 drop-in, the rollback
manifest, the base unit, broker/HA/ESP32 state, MQTT topics, packages, Docker,
network/storage/backups, or the pump.

## Acceptance and remaining boundary

A successful deployment proves only this #192 source/credential-path migration:

- tracked secret-free source is the running bot source;
- process argv is exactly the system Python plus the tracked source path;
- systemd credential references are the reviewed five fixed names/paths;
- K10 lifecycle identity remains accepted;
- service returns active/running after the one authorized restart.

This does **not** rotate or revoke the legacy shared MQTT credential. That remains
separate #189 work after all consumers are individually migrated and proven.
Likewise #194 delivery/client-ID semantics remain separate.
