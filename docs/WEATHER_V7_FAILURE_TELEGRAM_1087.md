# Weather v7 future-failure Telegram alert — source only (#1087)

Status: **SOURCE-ONLY; not installed or activated**. Owner decision on 2026-10-24:
`APPROVE RPi5_main #1087 FUTURE-V7-FAILURE-ALERTS=TELEGRAM NEW-OR-CHANGED-ONLY SOURCE-ONLY NO-LIVE`.

## Owner decision and accepted baseline

The historical `rozkalns-weather-operator-v7-dispatch-caller.service`
`failed/exit-code/78` from 2026-09-30 21:55:22 CEST is **accepted and retained**.
Its original journal is lost. Do **not** reset its failed state simply to
make the host report green. The caller's boot-only timer, with
`OnBootSec=2min` and `Persistent=false`, stays unchanged and non-retrying.
No source change explains the original exit 78 or makes the legacy dispatch path
a normal release mechanism. SIMPLE-DEPLOY remains the ordinary Weather path.

## Narrow notification architecture

When and **only when** that exact caller service newly transitions to systemd
`failed`, its `OnFailure=rozkalns-weather-v7-failure-telegram.service`
may launch one fixed, unprivileged notification helper. Installing the source
after an already failed incident does **not** replay that historical incident.
No generic failed-unit scanner, timer, broker, dispatcher, shell command,
owner-selected destination, or application execution is introduced.

The notifier reads fixed unit metadata with `systemctl show` (unit, result,
exit code/status and transition/exit timestamps); it requires `failed`,
a nonzero transition monotonic timestamp, and strictly validated fields.
A boot ID and incident transition/codes form a SHA-256 ledger filename.
The dynamic-user, private `StateDirectory` contains an `O_EXCL`, fsynced
`ATTEMPTED` receipt **before** one HTTPS Telegram API call. Repeated
invocation of the same incident does not send again. A different future
invocation/boot/result is eligible. The ledger has a bounded 256-entry budget;
there is no automatic retry, replay, cleanup, or replacement of historical
records. The receipt is appended with `TELEGRAM_API_ACCEPTED` only after
Telegram returns `ok=true`; API acceptance is **not** end-to-end chat delivery
proof. Network failures can drop the alert; that risk requires explicit
owner acceptance at the LIVE activation gate.

Two purpose-specific credentials come from systemd `LoadCredential`
only: `telegram-token` and `telegram-chat-id`. The reviewed unit names fixed
future protected host inputs:
`/etc/credstore/weather-v7-failure-telegram-token` and
`/etc/credstore/weather-v7-failure-telegram-chat-id`.
Those inputs are **not created, fetched, printed or modified** here.
The helper never uses the balcony irrigation bot, its MQTT command topics,
or its credential set. HTTP exceptions can include the bot token in a URL;
the helper logs **exception class only**, never exception message, token,
chat ID, payload or response body.

## Source delivery and separate LIVE gate

This source change adds:
- `ops/bin/rozkalns-weather-v7-failure-telegram`;
- `ops/systemd/rozkalns-weather-v7-failure-telegram.service`;
- a single `OnFailure` line in the **tracked source** v7 caller service;
- synthetic network-free tests included in `make test`.

**No existing host unit, binary, secret or credential is changed by source merge.**
Before any installer or credential provisioning, obtain separate explicit owner
LIVE approval with a fresh exact-main CI/SHA, installed caller identity,
service/timer baseline, secure credential-provisioning plan, exact artifact
install paths/ownership, proof that the historical failed state is retained,
dry-run-free synthetic validation, and a new-event acceptance plan that does
not induce a production failure. Both unit files and the helper need an
independently reviewed controlled install route; this PR does **not** provide
an authorization to use an ad hoc copy. The separately gated installer
source is defined in the continuation below.
Changing systemd state, `daemon-reload`, an actual Telegram send, service
restart, timer trigger, `reset-failed`, reboot or any protected runtime
inspection remains outside the source authorization.

Issue #1087 must stay open until its separate operational acceptance is
recorded. The accepted historical failed state must not be hidden.


## Bounded installer source (#1087 continuation)

`scripts/install-weather-v7-failure-telegram.py` and
`ops/deploy/weather-v7-failure-telegram-install-v1.json` define the
exact prospective operation. **Source delivery does not authorize runtime
preflight, credential inspection, or LIVE mutation.** Do not execute this
installer against RPi5 until fresh owner permission covers the exact action.

The command modes are intentionally distinct. The required SHA must bind a
**fresh verified merged main SHA**; it is never a standing authorization:

- Default `--expected-main-sha SHA`: offline source-only check of a
  clean canonical `main` checkout, expected Git origin, tracked
  source contents, boot-only timer, and exact target contract. No host read.
- `--host-preflight --expected-main-sha SHA`: separately authorized
  host read-only proof; exact old caller service contents, caller binary and
  timer identities; fixed root-owned target paths; two separately provisioned
  credential **file metadata only** (root:root 0600, never contents); and
  preserved accepted Sep-30 failed/78 state.
- `--apply --expected-main-sha SHA`: only under separate explicit
  owner LIVE authorization and root access. The first write consumes that
  authorization. Creates exactly the fixed notifier executable and unit,
  creates a fixed temporary caller-unit candidate then atomically replaces
  exactly that legacy caller service unit, and executes one
  `systemctl daemon-reload`. Afterwards, verify only exact artifact
  hashes and preserved failed/78 status. **No start, timer change, reboot,
  reset-failed, notification send, secret creation, cleanup, retry or rollback.**

The operator must first independently provide **purpose-specific notifier
credentials** to the two reviewed fixed `/etc/credstore/` paths
under a *different* explicit owner permission for secrets/credentials;
this installer neither derives nor reuses the balcony bot's tokens.
The installer intentionally fails closed if those files are absent. It does
not silently add credentials or promote source readiness to LIVE readiness.

**LIVE sequencing caution:** the future authorization must cover installing
two new files, one fixed staging file and atomic replacement of the caller
unit, plus one daemon reload and bounded metadata verification. Check
current main, required exact-main CI, installed previous unit hash,
caller/timer state and local source provenance **before** any write.
If any mutation fails or outcome becomes uncertain, STOP with only narrowly
allowed read-only evidence; no automated cleanup or second attempt. An
OnFailure hook can send on a *future* new failure; no production failure
is induced as a test. No public notification delivery is proven by this PR.
