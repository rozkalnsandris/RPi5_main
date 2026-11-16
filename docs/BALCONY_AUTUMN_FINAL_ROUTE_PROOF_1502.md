# 11:00 legacy watering Telegram route — final proof contract (#1502)

SOURCE ONLY. The checked source is NOT installed or run. **No HA, Telegram, MQTT,
credential, RPi5 runtime, actuator, or host mutation** is authorized here.

## What is already known and what is not

- At issue discovery main was b07dcd073b9e2dcbeb62e50b18bc9ae81055d49d,
  one unrelated Grafana commit after #1499. The last approved RPi5 checkout
  was 29e91e35e18320d60dc8972e88fac7c35f218867. These are
  **historical observations**; recheck main, checkout and release before use.
- PR #1496 delivered the 12-sensor 11:00 *notify-only* source, SHA-256
  7c993c5e0fdffdcb405b57aebad2be65a133be17caf13f16492fde6f12bc45b1.
  Do NOT use the separate 10-sensor controller as a route-only replacement.
  Missing sensors 5/11/13 may still block watering.
- PR #1499 delivered a source-only one-file replacement operator and read-only
  job preflight. Both were verified at RPi5 without writing any file.
- The separately authorized read-only RPi5 checks established: installed
  controller/job/wrapper hashes, enabled/local 11:00 schedule, disabled former
  jobs, successful current bot MQTT SUBACK and encrypted-credential **metadata**.
  No HA authentication was tested; no configured Telegram chat identity or
  human receipt was independently verified.
- An existing benign notification-only offline smoke plan is already tracked:
  ops/bin/balkons-bot-mqtt-notification-smoke-plan (#1486).
  **Reuse it. Do not introduce another publisher, bot or automation.**

## Minimal offline source check

Run: python3 -I -B ops/bin/balcony-autumn-final-route-proof-plan --check

The tool checks ONLY the fixed 12-sensor controller's exact source SHA,
single HA MQTT notification topic and route, bot notification subscription/
forwarding callback AST, and the existing smoke-plan topic/path/payload.
It reads only three public, allowlisted repository files. It creates no
runtime files, accesses no credentials, and has no network client. Its
SOURCE_ROUTE_CONTRACT_PASS means **only that the published source route
contract is coherent**. All live proof fields remain UNVERIFIED.

## Minimal independent proof before controller LIVE approval

1. **HA authentication / exact wrapper authority:** a *separately owner-
   authorized, trusted* read-only evaluator must test the actual effective
   Hermes HA identity against GET /api/, requiring authenticated HTTP 200
   with JSON {"message":"API running."}. The currently documented
   wrapper sources private Hermes environment. Its mere existence cannot
   prove the token's validity. Do not read, copy, hash or print that .env
   or export the token into argv, logs, GitHub, test tools or chat.
   **No reviewed trusted credential delegate is established today.**
   Until one exists, this check is BLOCKED, not implicitly PASS.
2. **Recipient binding:** separately trusted read-only Telegram checks
   getMe (the bot authenticated identity) and getChat (metadata for the
   configured chat), with output restricted to categorical matches against
   an independent owner-approved bot/chat identity. Never print/retain
   bot tokens, IDs, usernames, names, returned chat objects or API URLs
   containing tokens. The owner independently confirms the Telegram bot
   named "Balkona Laistīšana" is the actual target, not "RPi5 Paziņojumi".
   The phrase is a bot/conversation display name, **not** an automatic
   match against the getChat title field of a private chat.
   Existing systemd encrypted-credential files are forbidden to this
   offline checker; no delegate/secret-read authority is inferred.
3. **No duplicate senders:** via a separate narrow HA metadata gate,
   confirm no native HA Telegram automation is actively forwarding the
   same topic alongside the existing RPi5 bot. Source templates being
   disabled are insufficient to prove actual live config.
4. **Actual delivery, after separate explicit owner LIVE authorization:**
   use the **existing** fixed benign smoke-test plan only if its separate
   trusted one-shot publisher and credential delegation are reviewed and
   authorized (#1488). One fixed POST to balkons/telegram_out with qos=0
   and retain=false, never balkons/cmd, no retry. Require same-invocation
   SUBACK and source=mqtt Telegram HTTP API outcome plus the owner's
   independent exact-message receipt in the intended conversation.
   MQTT SUBACK, HTTP 200, Telegram API acceptance and bot identity alone
   are NOT human delivery proof. Alternatively, observe the next ordinary
   11:00 notification AFTER a separately authorized controller install.
   Do not manually run the controller as a probe.

Official documentation:
- HA read-only status/auth: https://contributors.home-assistant.io/core/internals/rest-api/
- Telegram getMe/getChat: https://core.telegram.org/bots/api

**STOP / BLOCKED before LIVE** whenever identity, effective HA access,
exclusive recipient, actuator state or safe source/host baseline remains
unverified. The source check does not widen any protected-runtime boundary.
A future controller replacement still requires separate exact owner
COMPOSITE STRICT LIVE approval. No automatic retry/rollback/cleanup.
