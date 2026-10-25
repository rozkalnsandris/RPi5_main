# Ausmalwiese GoatCounter isolated proof v2

Status: **SOURCE ONLY — NOT LIVE — NOT AN INSTALL OR RETRY AUTHORIZATION**

Issue: #1228.

This operator supersedes
`scripts/ausmalwiese_goatcounter_isolated_probe_v1.py` for every future
GoatCounter synthetic runtime proof. The v1 entrypoint remains historical
source and must not be used for another runtime attempt.

Canonical future entrypoint:

```text
python3 scripts/ausmalwiese_goatcounter_isolated_probe_v2.py --release-archive /tmp/goatcounter-v2.7.0-linux-arm64.gz
```

Running that command on `rpi5` still requires a new exact owner LIVE
authorization. Source merge alone authorizes no host execution.

## Why v2 exists

The first separately authorized v2.7.0 arm64 proof passed the pinned archive
verification, FF-only source sync and pageview source-contract check, then
stopped as:

```text
GOATCOUNTER_ISOLATED=STOP CODE=BINARY_COMMAND_REJECTED
```

The v1 operator deliberately discarded GoatCounter stdout/stderr but collapsed
all synthetic setup failures into one code. Its `TemporaryDirectory`
lifecycle could also remove the private fixture while unwinding a failure.
That made the failure safe but insufficiently diagnostic and did not preserve
failure evidence.

No retry of that runtime proof was part of #1228.

A later separately authorized v2 proof then localized the next failure to:

```text
GOATCOUNTER_ISOLATED=STOP CODE=SYNTHETIC_API_TOKEN_CREATE_FAILED
```

Pinned v2.7.0 source review showed that the inherited v1 setup passed a plain
email to `db create apitoken -user=...`. The upstream command first accepts
an email while resolving `site_id`, but then calls `User.Find()`, whose
non-numeric form expects a different selector shape. The canonical v2 operator
therefore reads the one synthetic numeric `user_id` from its private
isolated SQLite fixture and passes only that numeric ID to the API-token CLI
step. The ID is never printed or returned.

A third separately authorized proof progressed through setup and the two
synthetic count submissions, then stopped at shutdown as:

```text
GOATCOUNTER_ISOLATED=STOP CODE=SERVER_UNCLEAN_EXIT
```

Pinned GoatCounter v2.7.0 uses the pinned zhttp `Serve()` helper. zhttp
registers SIGHUP/SIGTERM/SIGINT with `signal.Notify()`, calls
`http.Server.Shutdown()`, and then GoatCounter runs
`cron.TaskPersistAndStat()` before its normal zero exit. Pinned zhttp also has
an explicit exit 66 for a Serve error; GoatCounter's force-kill path exits 99.

The observed generic failure did not prove which abnormal exit occurred.

A fourth separately authorized proof, after the first shutdown-classification
change, progressed through the same synthetic runtime path and stopped as:

```text
GOATCOUNTER_ISOLATED=STOP CODE=SERVER_OTHER_NONZERO_EXIT
```

Pinned GoatCounter v2.7.0 uses exit 1 for its generic command-error path.
Go's runtime uses exit 2 for an unrecovered panic/runtime failure by default.
The canonical v2 operator therefore distinguishes those two positive exits
without capturing or printing GoatCounter stdout/stderr.

A fifth separately authorized proof then stopped as:

```text
GOATCOUNTER_ISOLATED=STOP CODE=SERVER_GOATCOUNTER_COMMAND_ERROR
```

That established GoatCounter exit code 1, but the operator still used the same
return-code mapping whether the child had already exited before shutdown or
exited after the proof sent SIGINT. The result therefore did not prove that
shutdown caused the command error. The canonical v2 operator now performs one
process-state observation before any shutdown signal and reports a separate
pre-shutdown class when the child is already gone.

A sixth separately authorized proof then stopped as:

```text
GOATCOUNTER_ISOLATED=STOP CODE=SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR
```

That established that the child had exit code 1 before the proof requested
shutdown. It still did not prove that both synthetic count requests completed:
the count/readiness body ran inside a `try` whose `finally` always executed
the server-stop classifier. If a count-stage `RuntimeStop` was already
unwinding and the finalizer raised a server-stop `RuntimeStop`, Python would
propagate the finalizer exception and mask the original backend failure.

The canonical v2 operator now preserves the first readiness/count
`RuntimeStop` as primary evidence. It still executes the one bounded
server-stop path, but any secondary finalizer exception is reduced to a fixed
sanitized code and attached only as internal secondary evidence. The operator
stdout remains the primary stable failure code.

Upstream evidence also confirms the HTTP contract used by this proof:
GoatCounter documents `POST /api/v0/count` for backend pageview ingestion,
supports `no_sessions:true`, and pinned v2.7.0
`handlers/api.go` writes HTTP 202 on the successful count path before
returning `{"status":"ok"}`.

## Reused v1 security boundary

v2 imports and reuses the already reviewed v1 implementation for:

- the exact GoatCounter v2.7.0 Linux arm64 release pin;
- archive name, byte-size and SHA-256 verification;
- non-root `rpi5`/Linux/arm64 host guard;
- isolated environment construction;
- `version -json` build-profile validation;
- synthetic site creation and post-setup privacy configuration;
- loopback-only server readiness;
- the exact two synthetic `0427183` count submissions;
- one-transmission HTTP behavior with proxies and redirects disabled;
- the single graceful SIGINT shutdown attempt and timeout bounds;
- structural SQLite privacy validation.

v2 does not add a downloader, install path, production database path,
credential source, service mutation, Cloudflare operation or retry path.

## Stage-specific setup diagnostics

v2 executes the three synthetic setup stages directly with the same
stage-specific runner. After synthetic site/user creation it reads exactly one
matching synthetic `user_id` from the private fixture and uses that numeric
selector for API-token creation. Non-zero exits, execution errors and timeouts
map to one stable code according to the attempted setup stage:

| Synthetic stage | Stable code |
| --- | --- |
| database creation | `SYNTHETIC_DB_CREATE_FAILED` |
| site/user creation | `SYNTHETIC_SITE_CREATE_FAILED` |
| count-only API token creation | `SYNTHETIC_API_TOKEN_CREATE_FAILED` |

An unexpected setup command fails closed as
`SYNTHETIC_SETUP_STAGE_INVALID`.

For every setup command, stdin is disabled and stdout/stderr are sent to
`DEVNULL`. The operator never includes raw GoatCounter output, generated
synthetic credential values, SQLite rows or fixture paths in the failure code.
The selector lookup itself fails closed as `SYNTHETIC_DATABASE_SETUP` unless
exactly one positive integer synthetic user ID matches the fixed synthetic
email. No selector value is included in operator output.

## Shutdown exit classification

Before sending any shutdown signal, the proof performs exactly one
`proc.poll()` process-state observation.

If the child has already exited, no SIGINT is sent. The proof fails closed with
one stable pre-shutdown class:

| Pre-shutdown observed class | Stable code |
| --- | --- |
| clean exit 0 before shutdown was requested | `SERVER_PRE_SHUTDOWN_CLEAN_EXIT` |
| terminated by SIGINT before proof shutdown | `SERVER_PRE_SHUTDOWN_SIGINT_EXIT` |
| GoatCounter generic command-error exit 1 | `SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR` |
| Go panic/runtime-failure exit 2 | `SERVER_PRE_SHUTDOWN_GO_RUNTIME_FAILURE` |
| pinned zhttp Serve error exit 66 | `SERVER_PRE_SHUTDOWN_ZHTTP_SERVE_ERROR` |
| GoatCounter force-kill exit 99 | `SERVER_PRE_SHUTDOWN_FORCE_KILL_EXIT` |
| another negative signal return | `SERVER_PRE_SHUTDOWN_OTHER_SIGNAL` |
| another positive non-zero return | `SERVER_PRE_SHUTDOWN_OTHER_NONZERO_EXIT` |

A pre-shutdown exit is an unexpected phase failure even when its return code is
zero; a complete proof may pass only after the child was observed alive, the
proof sent its one graceful SIGINT, and the resulting process return code was
exactly zero.

If the child is still alive, the proof sends exactly one SIGINT and preserves
the existing post-SIGINT classes:

| Post-SIGINT observed class | Stable code |
| --- | --- |
| normal return code 0 | proof continues toward PASS |
| terminated directly by SIGINT | `SERVER_TERMINATED_BY_SIGINT` |
| GoatCounter generic command-error exit 1 | `SERVER_GOATCOUNTER_COMMAND_ERROR` |
| Go panic/runtime-failure exit 2 | `SERVER_GO_RUNTIME_FAILURE` |
| pinned zhttp Serve error exit 66 | `SERVER_ZHTTP_SERVE_ERROR` |
| GoatCounter force-kill exit 99 | `SERVER_FORCE_KILL_EXIT` |
| another negative signal return | `SERVER_TERMINATED_BY_OTHER_SIGNAL` |
| another positive non-zero return | `SERVER_OTHER_NONZERO_EXIT` |

The proof does not retry, send a second graceful signal, or accept a non-zero
post-SIGINT exit as success. The numeric return code, signal number, PID,
stdout/stderr and fixture path are not printed. Existing timeout handling
remains fail-closed: `SERVER_SHUTDOWN_TIMEOUT` after the bounded termination
path and `SERVER_PROCESS_STUCK` if even that process termination does not
complete. Those paths do not perform a proof retry.

## Failure evidence lifecycle

v2 creates one fixture with:

```text
tempfile.mkdtemp(prefix="goatcounter-offline-", dir="/tmp")
```

and immediately sets the fixture root mode to `0700`.

There is intentionally no `finally` cleanup around the proof. If archive
validation, version validation, setup, loopback serving, count submission,
shutdown or the SQLite privacy gate fails, execution exits before cleanup and
the private synthetic fixture remains under `/tmp/goatcounter-offline-*`.

That retained fixture is not permission to inspect or delete it. Any later
inspection or cleanup is a separate owner-authorized host operation.

Only a complete proof PASS reaches the bounded success cleanup
(`shutil.rmtree(root)`). A cleanup failure is not converted into proof PASS.

## One-attempt invariant

v2 adds no retry or fallback. Each synthetic setup command is invoked once.
The inherited HTTP count path still performs exactly one transmission per
synthetic hit, requires the pinned successful HTTP 202 response, and never
resends after ambiguity.

If readiness or counting raises a stable `RuntimeStop`, that first failure is
retained as the causal operator result even though the existing bounded
server-stop finalizer still runs. A later finalizer/server-stop failure cannot
replace it. Secondary server-stop evidence is restricted to the fixed known
shutdown classes; any unexpected secondary exception is reduced to
`SERVER_STOP_SECONDARY_ERROR`. No secondary code is printed by the operator.
A runtime failure terminates that proof attempt.

## Disconnected tests

```text
python3 tests/test-ausmalwiese-goatcounter-isolated-proof-v2.py
```

The tests use mocks and temporary synthetic directories only. They do not
execute GoatCounter or inspect RPi5 runtime state. They prove:

- exact v2.7.0 arm64 pin reuse;
- each setup-stage non-zero exit produces its own stable code;
- upstream stdout/stderr stay suppressed;
- execution errors remain stage-specific without leaking details;
- API-token creation uses the isolated numeric synthetic user ID;
- an already-exited child maps to a fixed pre-shutdown class and never receives SIGINT;
- pre-shutdown exits 0, 1, 2, 66, 99, other signals and other positive values map to sanitized fixed classes;
- a live child receives exactly one SIGINT and preserves all existing post-SIGINT mappings;
- only post-SIGINT return code zero allows the proof to continue toward PASS;
- `BACKEND_NOT_ACCEPTED` and `BACKEND_RESPONSE_UNCERTAIN` remain primary when a server-stop finalizer also fails;
- the observed backend-failure plus pre-shutdown GoatCounter exit-1 shape preserves the backend code and retains only sanitized secondary evidence;
- successful counts still allow the existing server-stop class to become the primary failure;
- the inherited count path still requires HTTP 202, uses `no_sessions:true`, and performs no retry;
- runtime failure skips cleanup and preserves a private `0700` fixture;
- complete PASS reaches success cleanup exactly once;
- operator output contains only the stable failure code;
- no downloader or production data path was introduced.

The existing v1 pageview and offline-privacy tests continue to cover the
underlying archive, HTTP, privacy and no-production-path invariants.

## Remaining gates

After this source is reviewed and merged, all runtime work remains separately
gated:

1. a fresh exact owner authorization for one v2 synthetic proof on `rpi5`;
2. review of the resulting sanitized PASS/STOP evidence;
3. service/path/port/credential provisioning compatibility;
4. German GDPR/TDDDG review;
5. separately authorized install/database/service work;
6. separately authorized exact path-only Cloudflare Tunnel ingress and public
   verification.

The `coloring-pages` GoatCounter client PR remains under its existing MERGE
HOLD until the required runtime, legal and LIVE gates are satisfied.
