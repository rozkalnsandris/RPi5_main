# Installed balcony Telegram bot — guarded public-source update (#1484)

**SOURCE ONLY.** No production change or LIVE authorization is implied by GitHub source, CI, a PR merge, or a CLI switch.

## Distinct from the completed initial install

The #925 initial-installer is strictly initial-create and rejects targets already present. The currently installed public Python source SHA-256 baseline is 53de789f18b2ef09558f5298ff3ea8f74e94020f3ce0622893e7123c225a36fd. The newer #1483 merged source adds privacy-safe MQTT broker SUBACK and Telegram Bot API acceptance events; these source changes have not yet been deployed on RPi5.

This outcome adds ops/bin/balkons-bot-installed-update-operator: a separate, one-shot installed-source update operator. It must be installed as a trusted root-owned, mode 0755 file at exactly /usr/local/sbin/rpi5-balkons-bot-installed-update-operator, with reviewed bytes identical to those in the exact merged commit. **Installing the trusted root operator is a separate owner-authorized LIVE mutation.**

## Read-only CHECK prerequisites

- Trusted owner checkout ~/RPi5_main: exact clean main and local origin/main equal the approved GitHub main, all five fixed source files match their immutable Git blob hashes. Execution from the mutable source checkout is rejected.
- Current public bot /usr/local/lib/rpi5-balkons-bot.py: root-owned regular one-link mode 0644; exact old SHA above; tracked candidate digest must match the separately owner-approved new source SHA.
- Existing root-owned mode 0644 public overlay at /etc/systemd/system/balkons-bot.service.d/95-rpi5-source-credentials.conf must match the reviewed public overlay SHA-256 3b696abc3ab96d4f088f18c73199e2671d60c00847214d96c467925d02900602. Existing K10 no-SIGKILL drop-in digest is 7dbc86f44abb3928da4f26fd272c4cf021d6e2d9d9809b9040f39123ff142662.
- Existing non-root balkons-bot-preflight must return exact PASS for the *old deployed public bot* with correct current GitHub SHA, user and unit fragment path fingerprints, active/running service, Restart=always, 10-second restart interval, 90-second timeout, SendSIGKILL=no, five encrypted credential metadata objects and no credential-content read/hash.
- Fixed parent directories are root-owned and not writable by others. Both /var/lib/rozkalns-balkons-bot-installed-update and /usr/local/lib/.rpi5-balkons-bot-installed-update-stage.py must be absent, including symlinks.
- A stable service MainPID and activation generation are required immediately before mutation. Read-only CHECK never writes anything or restarts a service. Previous runtime receipts are historical, not a future preflight.

## Distinct current owner authorization for APPLY

A bounded Composite STRICT LIVE owner decision is required separately. On APPLY, the operator also requires exactly one **new, owner-authored GitHub issue comment on #1484**, no older than 15 minutes, verified by read-only public GitHub GET with owner numeric ID 277435981. The JSON must have the exact fields and values below; arbitrary extra fields, wrong issue, stale timestamps and mismatched hashes fail closed.

```json
{
  "schema": "rozkalns.balkons-bot-installed-update-live-approval.v1",
  "issue": 1484,
  "target": "balkons-bot.service",
  "repo_sha": "<exact approved merged main SHA>",
  "old_source_sha256": "53de789f18b2ef09558f5298ff3ea8f74e94020f3ce0622893e7123c225a36fd",
  "new_source_sha256": "<approved current public bot SHA-256>",
  "overlay_sha256": "3b696abc3ab96d4f088f18c73199e2671d60c00847214d96c467925d02900602",
  "k10_sha256": "7dbc86f44abb3928da4f26fd272c4cf021d6e2d9d9809b9040f39123ff142662",
  "fragment_path_sha256": "<fresh reviewed service fragment fingerprint>",
  "service_user_sha256": "<fresh reviewed service user fingerprint>",
  "allow": [
    "backup_public_source",
    "atomic_replace_public_source",
    "restart_once",
    "postverify"
  ],
  "no_automatic_rollback": true
}
```

A past #925 comment, expired comment, assistant-generated comment without a current owner LIVE decision, and the --apply flag alone are **not** authorization. No LIVE comment is created in this source-only lane.

## Single approved update and fail-closed recovery

After independent owner authority, APPLY verifies the fresh GitHub-bound source, installed old public file, existing protected metadata through the non-root preflight, service lifecycle generation and fresh owner comment twice where appropriate. **First mutation:** exclusive root-only mode 0700 recovery directory. The former *public* Python source is preserved inside it as a mode 0600 file, with a sanitized SHA marker also mode 0600. Private legacy source, systemd configuration and credentials are never copied or read.

Then stage the new reviewed Python bytes in one exclusive root-owned file mode 0644 with O_EXCL and O_NOFOLLOW, verify their digest, reconfirm the old target digest, and atomically replace only /usr/local/lib/rpi5-balkons-bot.py. Flush and verify the installed file. **Exactly one systemctl restart balkons-bot.service. No daemon-reload.** The reviewed non-root deploy-verifier --verify must pass with exact deployed file, credential metadata, active process and argv shape.

After any error, timeout, drift or uncertainty following the first mutation: **STOP; no retry, automatic rollback, cleanup, second restart or alternate mutation.** Recovery folder presence blocks re-entry. Recovering old public source later requires a distinct reviewed and owner-authorized procedure and fresh service/provenance checks. The original public overlay, encrypted credential objects, K10, historical private unit and source stay untouched.

## Telegram and watering gates remain independent

Broker SUBACK only proves subscription acceptance for a particular connection. TG API outcome source=mqtt ok=1 means Telegram Bot HTTP API accepted the send, not confirmed human receipt. A local startup message or successful source test is **not** evidence of the MQTT route. New logs exist on RPi5 only after a separately authorized actual update; any post-install broker/Telegram observation requires its own owner-scoped read authorization.

The active 11:00 Hermès job/controller (#1474) must not be changed by this update. Its replacement still requires independent HA credential/sensor evidence, Telegram route validation and separate LIVE owner authorization. There are no MQTT publishes, Telegram probes, ESP32 changes or physical watering actions in this source outcome.

## Offline acceptance

The adversarial fake-root test tests/test-balkons-bot-installed-update-operator.py runs inside the existing balcony CI regression group through ci/validate-groups.json. It never contacts a real host, GitHub API, MQTT broker or Telegram. Exact-head CI, review and an explicit owner MERGE must precede any separately authorized host operation.
