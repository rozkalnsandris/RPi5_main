# dashboard_RPi5 #226 trusted-read bridge

Status: **SOURCE ONLY / DORMANT / NOT INSTALLED**

Canonical dashboard gate: `rozkalnsandris/dashboard_RPi5#226`.
RPi5_main source gate: `rozkalnsandris/RPi5_main#261`.

## Purpose

The dashboard #226 recovery helper is intentionally read-only, but it must read
protected host facts that the unprivileged deploy executor must never receive as
generic root/sudo/protected-tree authority. This bridge supplies one narrowly
pinned root read context for the exact current dashboard target and publishes
only the helper's already-reviewed public-safe receipt.

It is not a deploy executor operation, does not change
`ops/deploy/executor-operations.json`, and has no production release apply path.

## Exact dashboard source binding

This source gate is valid only for:

```text
REPOSITORY=rozkalnsandris/dashboard_RPi5
TARGET_SHA=3fcdd12db07bf2ef5504a3fa8fafe873d5b56c6d
```

The root bridge copies the staged source-control inputs into its private
`RuntimeDirectory`, verifies the copied bytes with `git hash-object --no-filters`,
and executes only the verified runtime copy. The staged files are therefore
never executed directly from the operator-writable cache.

| dashboard source path | exact Git blob |
|---|---|
| `tools/operator/issue226-readonly-recovery-preflight.sh` | `dcfee173c5f62b914428d5bcff1eba410358e626` |
| `tools/production-candidate-manifest.mjs` | `bea0f30602d119ae53b81e70ce2d4c283d369ce8` |
| `tools/package-terminal-native-runtime.mjs` | `f37c315dfda4ac00ed7dcf793fa8e2f44bfeff57` |
| `tools/production-release-controller.mjs` | `c501bea57c0d5c35e7961ae1f1e5593a02268661` |
| `ops/production/release-activation-contract.json` | `4b923e2282c6ddd7781495ac7e7ff02bcd09919f` |

A change to the dashboard target or any pinned source/control blob fails closed
and requires a new source review. The bridge never follows a moving branch.

## Fixed operator input layout

The bridge accepts no argv, browser path, GitHub path, environment override or
executor-supplied filesystem path. Its only input layout is the neutral fixed
staging root below:

```text
/var/cache/dashboard-rpi5-operator/
  issue226-3fcdd12db07bf2ef5504a3fa8fafe873d5b56c6d/
    source/
      tools/operator/issue226-readonly-recovery-preflight.sh
      tools/production-candidate-manifest.mjs
      tools/package-terminal-native-runtime.mjs
      tools/production-release-controller.mjs
      ops/production/release-activation-contract.json
    candidate/
      ... exact already-built production candidate ...
    candidate-manifest.json
    READY
```

This source PR does not create that staging root and does not choose or mutate
its host owner/group/mode. Those staging details must be frozen and reviewed in
the later exact host-installation envelope. The bridge service sees the staging
root read-only in its own systemd namespace.

`READY` is only a local trigger and carries no authority. Its exact contents are:

```text
SCHEMA=dashboard-rpi5.issue226-trusted-read-input.v1
TARGET_SHA=3fcdd12db07bf2ef5504a3fa8fafe873d5b56c6d
```

The candidate and manifest remain data. The bridge does not execute candidate
JavaScript, native binaries or shell content. The exact pinned helper/tool bundle
runs from the root-owned private runtime copy and verifies the candidate before
the release-controller PLAN is accepted.

## Execution boundary

Source blueprints:

- `ops/bin/rpi5-dashboard-issue226-readonly-bridge`;
- `ops/systemd/rpi5-dashboard-issue226-readonly-bridge.service`;
- `ops/systemd/rpi5-dashboard-issue226-readonly-bridge.path`.

Future installed mapping, **not authorized by this source gate**:

- bridge -> `/usr/local/sbin/rpi5-dashboard-issue226-readonly-bridge`;
- service/path -> matching `/etc/systemd/system/` unit names.

The service is root-owned only because the merged dashboard helper requires the
existing protected reads: cross-identity `/proc/<pid>/cwd`, root-owned installed
candidate markers and backup metadata, and the dedicated log-broker socket. The
service does not grant that authority to another identity.

Hardening keeps the operation read-bounded:

- `NoNewPrivileges=yes`;
- only `CAP_SYS_PTRACE` remains in the capability bounding set for cross-identity
  process CWD evidence;
- home and the fixed staging root are read-only to the service, and home is
  non-executable;
- system files are read-only;
- devices are closed;
- network is denied except localhost plus AF_UNIX for the existing broker;
- no supplementary group is added;
- no generic command, argv or path is accepted.

## Evidence boundary

Raw helper stdout/stderr is kept only in the private runtime directory. The
bridge allowlists the exact known helper keys, discards unknown/non-printable
lines, rejects duplicate keys for PASS, and requires all mutation flags to
remain `NO`.

Only one bounded public-safe receipt is atomically replaced:

```text
/var/lib/dashboard-rpi5/evidence/issue226-recovery-preflight.txt
```

The bridge adds its own schema/result metadata and preserves only allowlisted
helper fields. A PASS additionally requires:

- exact target/candidate/manifest binding;
- `CANDIDATE_MANIFEST_VERIFY=PASS`;
- `RELEASE_CONTROLLER_PLAN=PASS`;
- target release `absent`;
- exactly `copy_manifest_allowlisted_release,write_verified_manifest_marker,atomic_current_symlink_swap`;
- production/systemd/identity-permission/Docker-authority/Cloudflare/terminal
  mutation flags all `NO`;
- `RESULT=READ_ONLY_RECOVERY_PREFLIGHT_PASS`.

The evidence file write is a fixed sanitized receipt only; it is not a
production release, service, identity, permission, Docker, Cloudflare or
terminal mutation.

## Trigger semantics

The `.path` unit watches only the fixed `READY` file. It does not accept a
request payload. The operator stages all inputs first and changes `READY` last.
A staging-root creation/ownership decision, path/service install or enable is a
later host/systemd or permission mutation and requires a separate exact owner
authorization. Merge of this source gate does not perform any of those steps.

No automatic retry, rollback or production cleanup exists. A blocked bridge
receipt must be reviewed before any new trigger is written.

## Explicit exclusions

This bridge source has no path for:

- release-controller `--apply`;
- service start/stop/restart/reload/enable/disable/daemon-reload from the bridge;
- sudo or generic root shell access for the deploy executor;
- executor registry or executor activation changes;
- user/group/ACL/ownership changes to production inputs;
- Docker socket authority expansion;
- credentials/secrets/App permission changes;
- Cloudflare/network mutation;
- terminal activation/session creation;
- arbitrary protected file reads.

## Source validation and future gate

Normal `make validate` executes the dedicated bridge source-contract regression
through `tests/test-shell-syntax.sh`. The regression locks the target/blob pins,
fixed input/evidence paths, systemd hardening and unchanged disabled executor
registry.

After a separately authorized merge, exact-main CI must pass. A later owner gate
would still be required to create/freeze the neutral staging boundary and to
install/enable this bridge on the RPi5. Only after a fresh bridge PASS may
dashboard #226 freeze a new exact Composite Live recovery envelope and request
separate production authorization.
