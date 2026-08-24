# Balkons bot SendSIGKILL drift remediation

Issue: `RPi5_main#192`

Status: **source-only remediation design; no production authorization**.

## Why this artifact exists

The owner-authorized Phase K7 Composite STRICT transaction successfully advanced
the trusted RPi5 checkout to canonical source `31ad321746296bf52834edd8ef80cc256c2857d1`
and ran the reviewed `balkons-bot` production preflight.

The preflight was otherwise healthy but returned exactly one blocker:

- effective live `SendSIGKILL=yes`;
- expected tracked contract `SendSIGKILL=no`;
- blocker `send_sigkill_not_disabled`.

The same sanitized preflight proved that the service was loaded and active/running,
the service user was non-root, the critical Git paths were tracked and clean, the
historical live source provenance still matched
`54e7c58bae49a4a78fc033bd86eaa752cf21583bb86a0ba10d7ba9a617b1afd9`, and the
Paho compatibility probe succeeded on the existing runtime.

This is therefore a real tracked-contract versus effective-systemd drift, not a
source/preflight false positive.

## Remediation choice

The narrowest correction is a dedicated systemd drop-in:

`ops/systemd/balkons-bot-no-sigkill.conf`

Its complete service payload is only:

```ini
[Service]
SendSIGKILL=no
```

The reviewed operator is:

`ops/bin/balkons-bot-send-sigkill-remediation`

This artifact intentionally does **not** render or install the full future
`balkons-bot.service.in`, does not deploy the Git-tracked bot source, and does not
create/change credentials. It changes only the kill-policy setting that blocked
the read-only preflight.

## systemd semantics and conservative boundary

`SendSIGKILL=` controls whether systemd sends the final SIGKILL (or
`FinalKillSignal=`) after the normal stop timeout. systemd defaults it to `yes`.
The project contract deliberately requires `no`, because #192 forbids a SIGKILL
fallback.

`systemctl daemon-reload` reloads unit files and reconstructs the manager's unit
configuration. systemd documentation also notes that reloaded settings are not
universally guaranteed to take effect immediately for every property.

For that reason the remediation does not assume success after writing the drop-in:

1. run the existing reviewed preflight and require the **sole** blocker to be
   `send_sigkill_not_disabled` with live provenance still matching;
2. require the target drop-in path to be absent, so the operator never overwrites
   unknown local configuration;
3. install the exact reviewed drop-in;
4. run `systemctl daemon-reload`;
5. rerun the full reviewed preflight;
6. accept only a full `PASS`, including effective `SendSIGKILL=no`.

There is **no service restart** in this remediation. If the manager still reports
`SendSIGKILL=yes`, or any other preflight invariant changes, the transaction emits
BLOCKED evidence and stops. A restart is a separate production decision and must
never be added as an automatic fallback.

References:

- `systemd.kill(5)` — `SendSIGKILL=` kill-policy semantics;
- `systemctl(1)` — `daemon-reload` reloads systemd manager/unit configuration;
- `systemd.unit(5)` — reload replaces loaded configuration while runtime state is
  retained, with the documented caveat that some settings may not take effect
  immediately.

## Exact source bindings

Every operator invocation must bind all of the following:

- exact reviewed repository SHA;
- trusted checkout path fingerprint (SHA256 only; never print the private path);
- exact SHA256 of the remediation operator;
- exact SHA256 of `ops/bin/balkons-bot-preflight`;
- exact SHA256 of the reviewed drop-in;
- expected H3 live-source SHA256.

The operator additionally proves its own/drop-in/preflight files are Git-tracked
and clean before any mutation.

## Privilege separation

The trusted checkout is expected to remain owned by its normal non-root operator.
The remediation refuses a root-owned checkout.

In `--apply`/`--rollback` mode, root privilege is used only for the fixed systemd
filesystem change and `systemctl daemon-reload`. Git reads and the existing
`balkons-bot-preflight` are executed as the checkout owner through `runuser`, with
`GIT_OPTIONAL_LOCKS=0` so read-only Git checks do not opportunistically refresh the
index. The operator does not add or persist a Git `safe.directory` exception.

This keeps the same Git/read-only identity that successfully ran Phase K7 while
preserving root only for the explicitly owner-gated systemd mutation.

## Modes

### `--check`

Read-only. Requires the current full preflight to be BLOCKED with exactly
`send_sigkill_not_disabled`, effective `SendSIGKILL=yes`, and no provenance/write
violation. It also requires that the target drop-in does not already exist.

This mode is protected runtime inspection and therefore remains Composite STRICT
when executed on RPi5, despite being read-only.

### `--apply`

Production mutation. Requires root execution and a fresh successful `--check`
equivalent before mutation. The only intended writes/actions are:

- create the fixed service drop-in directory if absent;
- install the exact reviewed drop-in as root-owned mode `0644`;
- `systemctl daemon-reload`;
- rerun the existing sanitized preflight.

No restart/reload/stop/start/enable/disable/kill of `balkons-bot.service` is
performed. (`daemon-reload` is a systemd-manager configuration reload, not a
service reload.)

A future owner authorization is consumed at the first filesystem mutation.
Any error or ambiguity after that point requires evidence preservation and STOP.
There is no automatic rollback or cleanup.

### `--verify`

Read-only. Requires the installed drop-in to hash exactly to the reviewed source
and requires the full existing production preflight to PASS.

### `--rollback`

A **separately owner-authorized** recovery mode. It will only remove the fixed
reviewed drop-in when that installed file hashes exactly to the reviewed drop-in.
It never removes the drop-in directory or any other file. After removal it performs
`daemon-reload` and requires the exact original K7 condition to return: sole blocker
`send_sigkill_not_disabled`, effective value `yes`, and preserved live-source
provenance.

Rollback is not automatically invoked after an apply failure. Under the project
failure contract, a new explicit owner authorization is required after a mutation
has started and then failed or become ambiguous.

## Future Composite STRICT apply gate

A future apply authorization must bind at minimum:

- fresh canonical merged source SHA containing this artifact;
- target `RPi5 / balkons-bot.service`;
- the already selected trusted checkout fingerprint;
- remediation-operator SHA256;
- preflight SHA256;
- drop-in SHA256;
- expected H3 live-source SHA256;
- allowed mutation limited to exact drop-in install + `systemctl daemon-reload`;
- full read-only preflight before and after;
- explicit exclusions for service restart/reload/stop/start/enable/disable/kill,
  bot deployment, credential/broker/HA/ESP32/MQTT/Docker/package/network/storage/
  backup/pump mutation;
- STOP on any drift or error.

A successful remediation preflight PASS still does **not** authorize the actual bot
source/credential deployment. It only clears the observed lifecycle blocker so #192
can continue to the separately reviewed production deployment/rollback artifact.
