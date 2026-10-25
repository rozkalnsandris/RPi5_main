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
- graceful server shutdown;
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
synthetic hit and never resends after ambiguity. A runtime failure terminates
that proof attempt.

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
- the v1 runner is restored on setup failure;
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
