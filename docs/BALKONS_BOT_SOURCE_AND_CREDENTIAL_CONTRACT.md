# Balkons bot source and credential contract

Issue: `RPi5_main#192`

## Status and provenance

This document defines the **source-only** reconstruction of `balkons-bot.service`.
It does not authorize production deployment, a service restart, an MQTT credential
change, broker mutation, Home Assistant reconfiguration, ESP32 mutation, MQTT
publish, or a pump command.

Canonical H3 review inputs:

- H3 sanitizer artifact SHA256: `7cf763cd08f746cc2cd216bf4e0ede922011666762b119412585acfa228cd325`
- live bot source SHA256: `54e7c58bae49a4a78fc033bd86eaa752cf21583bb86a0ba10d7ba9a617b1afd9`
- sanitized source SHA256: `e322ed86fb044c799bef5f8f1c80840d7d78a3908665abc511d66aa966a74e9c`
- sanitized manifest SHA256: `21ec39d852b5945cb448480bf2c279d5f9202fe3b7c18287a98e9f0087fbad4e`

The H3 derivative is review evidence, not a deployable file. Its AST rendering
removed comments/formatting and intentionally redacted both private values and
some Telegram structural literals. The canonical source below reconstructs only
structure that can be supported by the H3 behavior and public protocol
documentation.

## Preserved behavior contract

The bridge keeps the existing topology:

- subscribe to `balkons/telegram_out` and forward received text to the authorized
  Telegram chat;
- publish accepted Telegram commands to `balkons/cmd`;
- preserve the existing `/laist`, `/laist_N`, `/stop`, `/mitrums`, `/statuss`,
  `/raw`, and `/start` command behavior;
- keep MQTT port `1883` and keepalive `60` to avoid an unrelated transport change;
- keep Telegram long polling with a 30 second server timeout and bounded retry
  after transient failures.

The ESP32 remains the authority for pump command safety. Its tracked firmware
bounds MQTT command payloads, treats `stop` as urgent, validates requested watering
minutes, and enforces the pump hard limit. The bot must not duplicate or broaden
that firmware safety policy in this source-provenance remediation.

## Runtime credential contract

The tracked source contains no credential values. At service activation systemd
provides five credential files through `$CREDENTIALS_DIRECTORY`:

- `telegram-token`
- `telegram-chat-id`
- `mqtt-host`
- `mqtt-username`
- `mqtt-secret`

The bot reads those files directly. Credential contents are never accepted via
process argv and are never copied into dedicated secret environment variables.
The environment variable used by application code is only systemd's directory
locator, `CREDENTIALS_DIRECTORY`.

The source unit template maps those credential names to root-managed files under
`/etc/credstore`. Production ownership, file creation, and value population are
outside this PR and require the later owner-gated deployment artifact.

## Why systemd credentials

systemd service credentials are made available as files below the per-service
credential directory for the duration of service activation. This avoids putting
credential contents into argv or ordinary environment variables and matches the
existing credential pattern already used by tracked RPi5 services.

References used for this reconstruction:

- systemd Credentials documentation: `https://systemd.io/CREDENTIALS/`
- Eclipse Paho Python client documentation: `https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html`
- Telegram Bot API: `https://core.telegram.org/bots/api`
- Requests quickstart: `https://requests.readthedocs.io/en/latest/user/quickstart/`

## Protocol reconstruction decisions

### Paho MQTT

The H3 snapshot used the historical four-argument `on_connect` callback shape.
The canonical source selects callback API `VERSION2` whenever the installed Paho
release exposes the versioned callback API, using the documented five-argument
callback form. A narrow four-argument compatibility callback remains only for a
Paho 1.x runtime that has no `CallbackAPIVersion` symbol. This avoids silently
requiring a production package upgrade while ensuring Paho 2.x does not use its
deprecated callback API v1. MQTT credentials are still supplied with
`username_pw_set()` before `connect()`.

The later production preflight must record only the installed Paho version/class
needed to select this path; it must not install or upgrade packages. This is a
source compatibility repair, not an MQTT topology or protocol migration.

### Telegram

The H3 snapshot proves use of `sendMessage` and `getUpdates`, but the sanitizer
redacted some dictionary keys. The canonical source restores only keys required by
the public Bot API contract:

- `sendMessage`: `chat_id` and `text`;
- `getUpdates`: `offset` and `timeout`;
- update sequencing: `update_id + 1`;
- authorization: compare `message.chat.id` with the credential-provided chat ID.

No Telegram token or chat ID is tracked.

### HTTP and logging

Every Telegram response is checked with `raise_for_status()`, parsed as JSON, and
required to contain `ok=true`. Request exceptions are logged only by exception
class, never by full exception text. This is intentional because HTTP exception
text can contain a request URL and the Telegram Bot API places the bot token in
that URL path.

The canonical bot also stops journaling raw Telegram command text and raw MQTT
payloads. Those values may contain personal or home telemetry data. MQTT payloads
are still forwarded to the authorized Telegram chat as required by existing
behavior; they are simply not duplicated into the system journal.

## systemd source template

`ops/systemd/balkons-bot.service.in` is intentionally **not directly installable**.
The following tokens must remain unresolved in Git:

- `@SERVICE_USER@`
- `@PYTHON_EXECUTABLE@`
- `@BOT_SOURCE_PATH@`
- `@RESTART_POLICY@`
- `@RESTART_SEC@`
- `@TIMEOUT_STOP_SEC@`

A later read-only production preflight must derive the current service lifecycle
and identity without exposing private paths or secrets. The production deployment
artifact then renders the template and binds the result to exact source and
artifact hashes.

The source template already requires `SendSIGKILL=no` and leaves the stop timeout
as a render-time lifecycle token; no deployment or rollback
plan may introduce a generic process kill or SIGKILL fallback.

## Source validation

The PR must pass the repository's normal `make validate` path, including public
safety and Gitleaks history checks. Additional tests require:

- Python AST/compile success;
- Paho callback API v2;
- exactly the five credential names above;
- no private LAN address or user-home path in bot source;
- no raw Telegram command/MQTT payload journal markers;
- no exception stringification;
- a fail-closed systemd template with unresolved deployment tokens;
- no auth flags or credential values in `ExecStart`/environment.

## Future production gate

Source review or merge does **not** authorize production.

Before any deployment, a separate reviewed artifact must perform a current,
sanitized, read-only preflight and bind authorization to:

1. the exact reviewed `RPi5_main` source SHA;
2. the exact production deployment artifact SHA256;
3. the still-expected live bot source provenance SHA or an explicitly reviewed
   successor state;
4. the current sanitized service lifecycle/identity contract;
5. a verified root-only rollback bundle.

Only a fresh narrow one-shot owner authorization may start mutation. Authorization
is consumed at `MUTATION_STARTED=YES` even if rollback follows.

## Rollback contract

The future deployment artifact must create and verify a root-only rollback bundle
before mutation. The bundle must preserve the pre-deploy live source, service
contract, and required runtime credential references without printing or
committing their contents or private paths.

If post-deploy validation fails, rollback must restore the exact pre-deploy files
and service contract, use only the named service lifecycle operation, and verify
that the bot returns to its pre-deploy MQTT consumer class. No generic `pkill`,
broad subscriber kill, SIGKILL fallback, broker restart, MQTT publish, ESP32
mutation, or pump command is part of rollback.

Legacy shared-account revocation remains blocked until the bot, Home Assistant,
and ESP32 migrations are separately proven complete.
