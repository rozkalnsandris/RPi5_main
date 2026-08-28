# Owner-authorized deploy executor v1 — P8 dry-run host preparation

Status: **P8 PREP SOURCE ONLY — NO HOST MUTATION**
Roadmap: `RPi5_main#236`

This source gate makes the already-authorized P8 host installation mechanically
installable without enabling production mutation. It does not itself place the
GitHub App private key on RPi5, create the service identity, install files,
reload systemd, start the poller, enable the timer, create LIVE-AUTH, dispatch a
deployment, retire any runner, or change DB/Cloudflare/production state.

## P7 identities carried into P8

The P8 read-only runtime is bound to the P7 App canary identities:

- GitHub App: `Rozkalns Deploy Executor`
- App ID: `4748870`
- Installation ID: `157217641`
- authorization repository: `rozkalnsandris/ops-workflows`
- stable repository ID: `1328835922`
- owner numeric GitHub ID: `277435981`
- repository installation scope: selected repository only
- effective repository permission: Issues read-only; Metadata implicit/read
- webhook: disabled
- GitHub write permission: none

The private key is never represented in this repository. The eventual P8 host
installer receives an absolute local key path and installs the key root-only at
`/etc/rozkalns-deploy-executor/github-app.pem`. The service receives a transient
systemd credential through `LoadCredential`; the key is not placed in an
environment variable, argv, state JSON, logs, GitHub issue, or repository.

## Installable dry-run runtime

Source layout added or activated by this gate:

- `ops/bin/rozkalns-deploy-poll`
- `ops/bin/rozkalns-deploy-dispatch`
- `ops/lib/deploy_executor/github_app_auth.py`
- `ops/lib/deploy_executor/p8_poller.py`
- `ops/deploy/executor-p8-dry-run-config.json`
- `ops/systemd/rozkalns-deploy-executor.service`
- `ops/systemd/rozkalns-deploy-executor.timer`
- `scripts/install-deploy-executor-p8-dry-run.sh`

The systemd service is a short-lived unprivileged oneshot. The timer starts one
poll about 30 seconds after activation and schedules subsequent polls two
minutes after the prior invocation becomes inactive. This prevents overlap and
keeps the polling cadence bounded.

Each poll:

1. reads the GitHub server `Date` header and creates a five-minute App JWT;
2. revalidates the exact installation ID, owner identity, selected-repository
   mode and lack of GitHub write permissions;
3. mints a short-lived installation token narrowed to repository ID
   `1328835922` and `issues:read`;
4. revalidates the `ops-workflows` repository numeric identity;
5. performs a bounded conditional GET of the newest open issues;
6. records only sanitized local status and ETag state.

A `304 Not Modified` is only a polling optimization. It is never accepted as
fresh authority for a future mutation.

## Hard P8 mutation disable

P8 intentionally has no production execution authority.

The poller requires the installed production registry to remain exactly
execution-disabled with zero operations before it performs a GitHub poll:

```json
{
  "schema_version": 1,
  "execution_enabled": false,
  "operations": []
}
```

The installed dispatcher entrypoint is an explicit fail-closed stub. It accepts
no execution request and exits with `DEPLOY_EXECUTOR_DISPATCH=DISABLED`.
There is no dispatcher service, Unix socket, sudoers grant, Docker socket,
generic shell bridge or poller-to-root IPC in this P8 source.

The GitHub result writer also remains disabled. Poll results are local evidence
only.

## Host installer boundary

`scripts/install-deploy-executor-p8-dry-run.sh` has a preflight-before-mutation
structure. Before its first host write it requires:

- execution as root under the separately authorized P8 live gate;
- an absolute regular private-key source with mode `0400` or `0600`;
- OpenSSL private-key validation;
- the exact P7 non-secret config identities above;
- the production registry to be exactly empty/disabled;
- all reviewed runtime/package/unit source files to exist and not be symlinks;
- any pre-existing service identity to have the expected non-login shell/group;
- all target paths to be absent, otherwise a fresh review is required.

After the first mutation, any command failure stops. The installer does not
perform automatic rollback, cleanup, reset or alternate-path recovery.

The installer creates only the dedicated service identity and fixed executor
paths, installs the root-only key, installs the reviewed systemd units, reloads
systemd, and verifies the installed unit with `systemd-analyze`. With
`--activate`, it performs one read-only service invocation and then enables the
two-minute timer.

## systemd boundary

The service preserves the P5 sandbox and adds systemd-managed credential/state
handling:

- dedicated `rozkalns-deploy-executor` user/group;
- `NoNewPrivileges=true`;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- `PrivateDevices=true`;
- empty capability bounding and ambient sets;
- restricted namespaces, proc and kernel surfaces;
- `SystemCallFilter=@system-service`;
- writable path only `/var/lib/rozkalns-deploy-executor`;
- root-only source credential injected with `LoadCredential`;
- no sudo or Docker socket.

The source test runs `systemd-analyze security --offline=yes` when the command
is available. P8 host activation must run the same analysis against the actual
installed unit on the actual RPi5 systemd version; source CI is not a substitute
for that host evidence.

## P8/P9 boundary

This source does **not** accept a LIVE-AUTH as production authority and does not
parse one into an executable operation. It only detects matching open issue
titles for dry-run polling evidence.

P8 exit, after a separately authorized host activation, is limited to:

- credential placement and service identity/path creation;
- exact reviewed source installation;
- sandbox verification;
- authenticated read-only polling working;
- production registry still empty/disabled;
- dispatcher still disabled;
- `PRODUCTION_MUTATION_STARTED=false`.

P9 remains a separate genuine read-only authorization canary. No dummy or
placeholder authorization issue may be created just to exercise P8/P9.
