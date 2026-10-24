# Weather v7 future-failure Telegram alert — source only (#1087)

Status: **SOURCE-ONLY; not installed or activated**. Owner decision on 2026-10-24:
\`APPROVE RPi5_main #1087 FUTURE-V7-FAILURE-ALERTS=TELEGRAM NEW-OR-CHANGED-ONLY SOURCE-ONLY NO-LIVE\`.

## Owner decision and accepted baseline

The historical \`rozkalns-weather-operator-v7-dispatch-caller.service\`
\`failed/exit-code/78\` from 2026-09-30 21:55:22 CEST is **accepted and retained**.
Its original journal is lost. Do **not** reset its failed state simply to
make the host report green. The caller's boot-only timer, with
\`OnBootSec=2min\` and \`Persistent=false\`, stays unchanged and non-retrying.
No source change explains the original exit 78 or makes the legacy dispatch path
a normal release mechanism. SIMPLE-DEPLOY remains the ordinary Weather path.

## Narrow notification architecture

When and **only when** that exact caller service newly transitions to systemd
\`failed\`, its \`OnFailure=rozkalns-weather-v7-failure-telegram.service\`
may launch one fixed, unprivileged notification helper. Installing the source
after an already failed incident does **not** replay that historical incident.
No generic failed-unit scanner, timer, broker, dispatcher, shell command,
owner-selected destination, or application execution is introduced.

The notifier reads fixed unit metadata with \`systemctl show\` (unit, result,
exit code/status and transition/exit timestamps); it requires \`failed\`,
a nonzero transition monotonic timestamp, and strictly validated fields.
A boot ID and incident transition/codes form a SHA-256 ledger filename.
The dynamic-user, private \`StateDirectory\` contains an \`O_EXCL\`, fsynced
\`ATTEMPTED\` receipt **before** one HTTPS Telegram API call. Repeated
invocation of the same incident does not send again. A different future
invocation/boot/result is eligible. The ledger has a bounded 256-entry budget;
there is no automatic retry, replay, cleanup, or replacement of historical
records. The receipt is appended with \`TELEGRAM_API_ACCEPTED\` only after
Telegram returns \`ok=true\`; API acceptance is **not** end-to-end chat delivery
proof. Network failures can drop the alert; that risk requires explicit
owner acceptance at the LIVE activation gate.

Two purpose-specific credentials come from systemd \`LoadCredential\`
only: \`telegram-token\` and \`telegram-chat-id\`. The reviewed unit names fixed
future protected host inputs:
\`/etc/credstore/weather-v7-failure-telegram-token\` and
\`/etc/credstore/weather-v7-failure-telegram-chat-id\`.
Those inputs are **not created, fetched, printed or modified** here.
The helper never uses the balcony irrigation bot, its MQTT command topics,
or its credential set. HTTP exceptions can include the bot token in a URL;
the helper logs **exception class only**, never exception message, token,
chat ID, payload or response body.

## Source delivery and separate LIVE gate

This source change adds:
- \`ops/bin/rozkalns-weather-v7-failure-telegram\`;
- \`ops/systemd/rozkalns-weather-v7-failure-telegram.service\`;
- a single \`OnFailure\` line in the **tracked source** v7 caller service;
- synthetic network-free tests included in \`make test\`.

**No existing host unit, binary, secret or credential is changed by source merge.**
Before any installer or credential provisioning, obtain separate explicit owner
LIVE approval with a fresh exact-main CI/SHA, installed caller identity,
service/timer baseline, secure credential-provisioning plan, exact artifact
install paths/ownership, proof that the historical failed state is retained,
dry-run-free synthetic validation, and a new-event acceptance plan that does
not induce a production failure. Both unit files and the helper need an
independently reviewed controlled install route; this PR does **not** provide
a privileged installer or authorization to use an ad hoc copy.
Changing systemd state, \`daemon-reload\`, an actual Telegram send, service
restart, timer trigger, \`reset-failed\`, reboot or any protected runtime
inspection remains outside the source authorization.

Issue #1087 must stay open until its separate operational acceptance is
recorded. The accepted historical failed state must not be hidden.
