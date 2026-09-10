# Weather privileged install/activation bridge

Issue #455 adds the missing **source-only** capability boundary needed after the
first public Weather Composite LIVE attempt stopped before helper installation.

The prior LIVE left the original trusted checkout present at an older exact SHA.
That checkout is evidence only and is never reset, updated, removed or cleaned.
A future fresh Composite LIVE uses the fixed successor checkout derivation:

`RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted`

The successor checkout may be created only by the existing bounded
`git.trusted-checkout-fetch <= 1` and `git.trusted-checkout-worktree-add <= 1`
classes and must end exact-SHA, detached, clean and on the reviewed origin. The
privileged entrypoint derives the actual checkout root from its own trusted
source location; no caller-controlled path or environment variable supplies it.

## Privileged capability

The only caller-controlled value is a positive `authorization_issue_number`.
The source entrypoint is fixed:

`ops/bin/rozkalns-weather-public-runtime-privileged-install`

A future host invocation is valid only from the exact successor trusted checkout
and as root. The entrypoint does not accept a command, source/destination path,
repository URL, argv vector, environment, helper ID, model, station, Docker
target, systemd unit or database path.

Before mutation the bridge reuses the existing Composite canonical revalidator,
isolated authorization/queue GitHub-App readers, credential-free fixed public
source reader, sanitized first-install baseline, exact helper manifest and
durable replay database. It then validates the successor checkout against the
authorized exact `RPi5_main` SHA.

The one-shot mutation boundary durably consumes the LIVE authorization before
the first install write. It installs exactly the 13 manifest artifacts to the
reviewed `/usr/local/libexec` destinations and then publishes exactly
`/etc/rozkalns-weather/public-runtime-helper-activation.json`, root:root `0600`,
bound to the complete canonical preactivation SHA-256 and fixed helper IDs.

No stage helper is invoked by this bridge. Release materialization, Docker,
systemd, SQLite schema/backfill, corpus integrity and recurring ingest remain
separate later Composite gates. There is no automatic retry, cleanup, rollback
or alternate route after the mutation boundary.

## Source/live separation

Source merge keeps all execution flags inactive. It does not install the
successor checkout, helper or activation file and does not authorize root
execution. A later human owner must create a **fresh** Composite STRICT
LIVE-AUTH bound to the then-current exact Weather/RPi5_main source and fresh
host baseline. Spent/expired `deploy-authorizations#18` is never reusable.

Machine contracts:

- `ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json`
- `ops/deploy/weather-public-runtime-privileged-install-activation.json`
