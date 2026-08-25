# Balkons bot production deployment and rollback contract

Issue: `RPi5_main#192`

Status: **source-only deployment design; no production authorization**.

## Purpose and accepted baseline

Phase K10 removed the effective-systemd lifecycle blocker and proved the current
`balkons-bot.service` baseline is loaded, active/running, non-root, still executing
the reviewed H3 historical live source, and effective `SendSIGKILL=no` without a
service restart.

This document defines the next source-only layer: an exact additive deployment of
the reviewed secret-free bot source and its systemd credential references. Nothing
here authorizes a host write, credential read/change, service restart, MQTT
operation, broker change, Home Assistant change, ESP32 change, or pump command.

## Additive deployment design

The deployment does not replace, copy, or read the raw live base unit and does not
copy the historical secret-bearing Python source. Those objects remain untouched.
The forward change is limited to two public reviewable files:

1. `/usr/local/lib/rpi5-balkons-bot.py`
   - exact bytes of tracked `ops/lib/balkons-bot.py`;
   - regular, non-symlink, root-owned, mode `0644`.
2. `/etc/systemd/system/balkons-bot.service.d/95-rpi5-source-credentials.conf`
   - exact bytes of tracked `ops/systemd/balkons-bot-runtime-override.conf`;
   - regular, non-symlink, root-owned, mode `0644`.

The K10 `90-rpi5-no-sigkill.conf` remains untouched. Rollback is therefore
removal-only for the two forward files and never needs a raw unit/source backup.

## Runtime overlay

The overlay establishes a deterministic tracked execution environment while
preserving the private service identity and K10 lifecycle values:

- clear `ExecStartPre=`, `ExecStart=`, `ExecStartPost=`, `ExecReload=`, `ExecStop=`
  and `ExecStopPost=` lists; then set exactly
  `/usr/bin/python3 /usr/local/lib/rpi5-balkons-bot.py`;
- reset `LoadCredential=` and add exactly the five reviewed credential names;
- clear `Environment=`, `EnvironmentFile=` and `PassEnvironment=` sources; then add
  only `PYTHONDONTWRITEBYTECODE=1`;
- use `UnsetEnvironment=` for the known historical/canonical credential-variable
  names without inspecting any environment values;
- keep `SendSIGKILL=no` and apply the tracked non-secret hardening directives;
- do not redefine `User=`, `Restart=`, `RestartSec=`, `TimeoutStopSec=`, enablement,
  dependencies, broker settings, or any private identity value.

The five fixed credential source paths are:

- `/etc/credstore/balkons-bot-telegram-token`
- `/etc/credstore/balkons-bot-telegram-chat-id`
- `/etc/credstore/balkons-bot-mqtt-host`
- `/etc/credstore/balkons-bot-mqtt-username`
- `/etc/credstore/balkons-bot-mqtt-secret`

No credential content appears in Git, argv, the overlay, verifier output, rollback
manifest, or deferred deployment queue.

## Credential prerequisite — separate STRICT gate

This workstream does not provision, recover, rotate, or inspect credential values.
Before the first future deployment mutation, separately owner-authorized STRICT
preflight must inspect metadata only and fail closed unless every fixed credential
file is:

- present at the exact fixed path;
- a regular non-symlink file;
- root-owned;
- mode `0400` or `0600`;
- non-empty and no larger than 4096 bytes.

Credential contents must not be opened, hashed, copied or printed. The same gate
must query effective `LoadCredential` metadata in memory and accept only an empty
current list; output is only `EMPTY`/`NONEMPTY`, never the raw entries. No equivalent
environment-content inspection is needed or permitted because the overlay clears
unit environment sources and uses `UnsetEnvironment=` for known secret names.

Supplying or changing credential values is a separate owner-managed secret
operation. Merge, `turpini`, `GITHUB-ONLY` and `LIVE-ALL` do not authorize it.

## Read-only deployment verifier

Tracked artifact: `ops/bin/balkons-bot-deploy-verifier`.

The verifier is deliberately non-root and read-only. Its executable shebang is
pinned to `/usr/bin/python3 -I`, every subprocess receives a minimal fixed
environment, Git/systemd commands use fixed `/usr/bin` paths, and the nested
production preflight is invoked explicitly as `/usr/bin/python3 -I <preflight>`.
This prevents user-writable checkout/import or inherited-environment shadowing from
becoming part of the trusted verification path.

### `--check`

Before deployment it requires:

- exact reviewed repository SHA on branch `main`;
- exact trusted checkout fingerprint and checkout-owner execution;
- verifier/source/overlay/preflight paths Git-tracked, clean and SHA256-bound;
- exact K10 drop-in root-owned mode-0644 hash;
- both forward targets absent;
- complete production preflight PASS against the H3 historical live-source SHA;
- K10 service identity/lifecycle hashes and values unchanged.

Success returns `READY`, `credential_content_read=false`,
`mutation_started=false`, and `writes_performed=false`.

### `--verify`

After an authorized deployment/restart it additionally requires:

- both forward targets regular non-symlink root-owned mode-0644 and exact hashes;
- complete production preflight PASS with the tracked source SHA256 as expected
  live-source provenance;
- unchanged service user, fragment, system Python and K10 lifecycle contract;
- stable `MainPID` across one bounded `/proc/<MainPID>/cmdline` read;
- process argv exactly `/usr/bin/python3` and
  `/usr/local/lib/rpi5-balkons-bot.py`.

Raw argv and process environment are never printed/read respectively.

## Root trust boundary

No repository executable is to execute or be copied as root. The privileged part
of any future Composite STRICT transaction must use fixed system binaries and exact
reviewed public bytes/hashes only. The non-root verifier first proves exact
Git/artifact bindings; the root segment then materializes only the bound public
source/overlay bytes and independently verifies target owner/mode/SHA256 before a
`daemon-reload` or restart.

## Root-only rollback manifest

Before the first forward file is created, the future transaction must create and
verify:

`/var/lib/rpi5-rollback/issue192-balkons-bot-v1.json`

The parent directory is root-owned mode `0700` if created; the manifest is regular,
non-symlink, root-owned mode `0600`. It contains only public identifiers, hashes and
boolean pre-state facts. It must bind at least:

- exact repository SHA;
- verifier/source/overlay/preflight/K10-drop-in SHA256 values;
- exact two forward target paths and proof both were absent immediately before
  forward mutation;
- K10 sanitized identity/lifecycle hashes;
- expected H3 historical live-source SHA256.

The manifest is evidence and a rollback authorization input, never automatic
rollback.

## Deferred deployment queue

The accepted `GITHUB-ONLY / LIVE-ALL v1` policy requires deferred rollout state to
live in public-safe `[DEPLOY-QUEUE]` issues in `rozkalnsandris/ops-workflows`, not
chat or memory.

For this workstream the queue item is `ops-workflows#13`. While this PR is unmerged,
it remains `[DEPLOY-QUEUE][WAITING]` with `WAITING_MERGE`. Even after merge it must
remain `WAITING` while the separate credential prerequisite is outstanding.

This rollout is classified `COMPOSITE_STRICT_SEPARATE_GATE`, not an ordinary
`LIVE-ALL` item while credential/secret work or another prerequisite owner decision
is required. PR Ready-for-merge is never deploy-queue READY.

After explicit merge, safe GitHub-only reconciliation must:

1. replace `WAITING_MERGE` with the exact merged/current deployable SHA;
2. compute exact merged verifier/source/overlay/preflight hashes;
3. bind the reviewed verifier as the repository preflight/verification entrypoint;
4. prepare/hash the exact separately owner-gated transaction artifact if needed;
5. re-evaluate the credential prerequisite;
6. keep the queue `WAITING` unless no separate prerequisite owner gate remains.

No private checkout path, credential value, protected configuration or sensitive
log may be placed in the public queue.

## Future Composite STRICT forward sequence

Only after source review, explicit merge, post-merge reconciliation and a fresh
owner authorization may one fail-closed transaction proceed. It must bind the exact
merged SHA, target alias, trusted checkout identity, transaction artifact where
used, component SHA256 values, K10 baseline, fixed targets and exclusions.

Intended sequence:

1. fresh GitHub/source reconciliation;
2. non-root deployment verifier `--check`;
3. separately authorized metadata-only credential readiness and effective
   `LoadCredential=EMPTY` gate;
4. immediate exact SHA/target-absence revalidation;
5. create and verify the root-only rollback manifest;
6. materialize exact reviewed source target;
7. materialize exact reviewed overlay target;
8. verify both owner/mode/SHA256 values;
9. exactly one `systemctl daemon-reload`;
10. exactly one `systemctl restart balkons-bot.service`;
11. non-root deployment verifier `--verify`.

Authorization is consumed at the first authorized host mutation. Any error, drift
or ambiguity after that point preserves sanitized evidence and STOPs. No automatic
retry, cleanup, rollback, alternate path, generic kill or SIGKILL fallback exists.

## Separately authorized rollback

Rollback is never automatic and requires fresh owner authorization. It first
verifies the root-only manifest and exact forward hashes, then may:

1. remove only the exact `95-rpi5-source-credentials.conf` target;
2. remove only `/usr/local/lib/rpi5-balkons-bot.py`;
3. run one `systemctl daemon-reload`;
4. run one `systemctl restart balkons-bot.service`;
5. run the already-reviewed K10 verifier to prove the historical H3 source is active
   again with effective `SendSIGKILL=no`.

Rollback must not alter credential files, the K10 drop-in, rollback manifest, base
unit, broker/HA/ESP32 state, MQTT topics, packages, Docker, network/storage/backups,
or pump state.

## Acceptance and remaining boundary

A successful deployment proves only the #192 source/credential-path migration:
tracked secret-free source is running, argv is exactly the system Python plus the
tracked source path, systemd credential references are the reviewed five fixed
names/paths, K10 lifecycle identity remains accepted, and the service is
active/running after the one authorized restart.

It does not rotate or revoke the legacy shared MQTT credential; that remains #189.
Delivery/client-ID semantics remain separate #194 work.
