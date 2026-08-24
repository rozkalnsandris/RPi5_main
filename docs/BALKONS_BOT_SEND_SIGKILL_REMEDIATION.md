# Balkons bot SendSIGKILL drift remediation

Issue: `RPi5_main#192`

Status: **source-only remediation design; no production authorization**.

## K7 evidence and problem statement

The owner-authorized Phase K7 Composite STRICT transaction advanced the trusted
RPi5 checkout to canonical source `31ad321746296bf52834edd8ef80cc256c2857d1`
and ran the reviewed `balkons-bot` production preflight.

The preflight was otherwise healthy but returned exactly one blocker:

- effective live `SendSIGKILL=yes`;
- expected tracked contract `SendSIGKILL=no`;
- blocker `send_sigkill_not_disabled`.

The same sanitized preflight proved the service was loaded and active/running, the
service user was non-root, critical Git paths were tracked and clean, the H3 live
source provenance still matched
`54e7c58bae49a4a78fc033bd86eaa752cf21583bb86a0ba10d7ba9a617b1afd9`, and the
existing Paho compatibility probe succeeded.

The tracked `balkons-bot.service.in` already requires `SendSIGKILL=no`. The K7
result is therefore a real tracked-contract versus effective-systemd drift.

## Minimal reviewed state

The desired drop-in is exactly:

```ini
[Service]
SendSIGKILL=no
```

Tracked source:

`ops/systemd/balkons-bot-no-sigkill.conf`

No other systemd setting belongs in this remediation.

## Root trust-boundary correction

An earlier draft design placed `--apply` and `--rollback` modes in a shell script
stored inside the normal user-owned Git checkout. Although that draft performed
self-hash checks, a shell script necessarily begins executing before it can verify
its own hash. Executing a user-writable checkout script as root would therefore
weaken the exact-artifact binding with a pre-verification/TOCTOU window.

That draft is superseded. The reviewed tracked executable is now deliberately
**read-only and non-root only**:

`ops/bin/balkons-bot-send-sigkill-verifier`

It has only two modes:

- `--check`: prove the exact K7 baseline before any future mutation;
- `--verify`: prove the exact installed drop-in and full preflight PASS afterward.

It refuses root execution and refuses execution by anyone other than the checkout
owner. It uses `GIT_OPTIONAL_LOCKS=0` for read-only Git checks. It contains no
install/remove operation, no `daemon-reload`, no service lifecycle action and no
root privilege transition.

The future Composite STRICT transaction must **not execute or copy a user-writable
repo executable as root**. The root mutation segment must use only explicitly
reviewed fixed system binaries and fixed drop-in bytes supplied by the transaction
itself. The installed root-owned target must be hashed and matched to the reviewed
drop-in SHA256 **before** `systemctl daemon-reload` is allowed.

This keeps the trust sequence fail-closed:

1. non-root exact verifier `--check` proves K7 baseline and exact Git/artifact
   bindings;
2. owner authorization is consumed only when the first root filesystem mutation
   actually starts;
3. root materializes only the two reviewed drop-in lines at the fixed target;
4. root verifies exact target ownership/mode/SHA256;
5. only then may root run `systemctl daemon-reload`;
6. non-root exact verifier `--verify` reruns the full reviewed preflight and accepts
   only effective `SendSIGKILL=no` with no other blocker;
7. any error or ambiguity after mutation starts preserves evidence and STOPs; no
   automatic cleanup, rollback or restart.

## systemd semantics

`SendSIGKILL=` controls whether systemd sends the final SIGKILL (or
`FinalKillSignal=`) after the normal stop timeout. systemd defaults it to `yes`.
The #192 contract intentionally requires `no` because this workstream forbids a
SIGKILL fallback.

`systemctl daemon-reload` reloads systemd manager/unit configuration. Because not
every setting is guaranteed to become effective immediately in every situation,
the transaction must not infer success merely from a successful daemon-reload. The
existing complete production preflight remains the acceptance gate.

There is **no service restart** in the planned remediation. If effective
`SendSIGKILL` remains `yes` after daemon-reload, or any other invariant changes,
the transaction stops. A restart would be a separate owner decision and is not an
automatic fallback.

References:

- `systemd.kill(5)` — `SendSIGKILL=` semantics and default;
- `systemctl(1)` — `daemon-reload` manager/unit reload semantics;
- `systemd.unit(5)` — unit reload/runtime-state behavior and applicability caveat.

## Verifier bindings

Every invocation must bind:

- exact reviewed/merged repository SHA;
- trusted checkout path fingerprint, represented only by SHA256;
- exact verifier SHA256;
- exact existing `balkons-bot-preflight` SHA256;
- exact reviewed drop-in SHA256;
- expected H3 live-source SHA256.

The verifier proves the verifier/preflight/drop-in source paths are Git-tracked and
clean before protected runtime inspection.

### `--check`

Read-only. It requires:

- execution as the non-root checkout owner;
- exact repository SHA and `main` branch;
- exact checkout/verifier/preflight/drop-in hashes;
- safe fixed drop-in-directory metadata if that directory already exists;
- the fixed target drop-in to be absent;
- the full existing production preflight to be BLOCKED with exactly
  `send_sigkill_not_disabled`, effective `SendSIGKILL=yes`, preserved live-source
  provenance, and no write/mutation markers.

### `--verify`

Read-only. It requires:

- all source/Git bindings above;
- fixed target to be a non-symlink regular file owned by root, mode `0644`;
- target SHA256 to equal the exact reviewed drop-in SHA256;
- the full existing production preflight to PASS;
- effective `SendSIGKILL=no` and zero blockers.

Both modes emit only sanitized preflight evidence plus public hashes/status markers.
They perform no host writes.

## Future Composite STRICT apply transaction

No production operation is authorized by this document or by source merge.

After this source is reviewed and merged, the future owner authorization must bind
at minimum:

- fresh canonical merged `RPi5_main` SHA;
- target `RPi5 / balkons-bot.service`;
- trusted checkout fingerprint;
- verifier SHA256;
- preflight SHA256;
- drop-in SHA256;
- H3 live-source SHA256;
- pre-change `--check` protected read-only inspection;
- root mutation limited to the fixed drop-in path and exact two-line content;
- target ownership/mode/hash verification before `daemon-reload`;
- one `systemctl daemon-reload` only;
- post-change non-root `--verify`;
- explicit exclusion of service restart/reload/stop/start/enable/disable/kill, bot
  source deployment, credential/broker/HA/ESP32/MQTT/Docker/package/network/storage/
  backup/pump mutation;
- STOP on any drift or error.

A PASS clears only the observed lifecycle blocker. It does not deploy the tracked
bot source or credentials.

## Separate rollback contract

Rollback is never automatic. If a future apply started and then failed or became
ambiguous, the project failure contract requires evidence + STOP and a new owner
authorization.

A separately authorized rollback must first use `--verify` when the forward state
is still fully accepted, or otherwise perform an equivalently strict read-only
identity/hash gate for the fixed target. Root may remove only that exact reviewed
target, run one `daemon-reload`, and then the non-root `--check` must prove the
original K7 state has returned. No directory cleanup, service restart, generic kill,
or alternate recovery path is implied.
