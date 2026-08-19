# Balcony MQTT logger cleanup stdin note

Issue: #173

The lifecycle-aware production attempt on 2026-08-19 reached a clean managed logger start and then failed closed during the explicit stop/start acceptance test with `LIFECYCLE_STOP_PROCESS_REMAINED`. Automatic rollback passed and restored one functional legacy logger instance.

The post-rollback read-only argv0 diagnostic showed one legacy `mosquitto_sub` process and confirmed that its argv0 is already the exact `mosquitto_sub` token. The earlier argv0 matcher hypothesis is therefore rejected.

The actual source defect is in the managed cleanup transport. `cleanup_container_subscriber` sends a shell helper to `docker exec ... sh -s` using a heredoc, but the pre-fix command omitted Docker's `-i` flag. Without an attached stdin, the helper body is not guaranteed to reach the container shell, so the cleanup path can return without running the in-container PID matcher/`SIGTERM` logic.

The reviewed fix is deliberately narrow:

- use `docker exec -i` for the cleanup helper transport;
- keep the exact managed client-id + logger-topic matcher unchanged;
- keep targeted `SIGTERM` only and the existing bounded wait;
- keep generic `pkill`, SIGKILL, broker/container restart, MQTT publish, ESP32 mutation, and pump command forbidden;
- strengthen the offline Docker mock so cleanup is recognized only when `-i` is present.

This note is source documentation only. It authorizes no production mutation. A new exact-main build, fresh read-only gate, new bound cutover artifact, and fresh explicit owner authorization are required before another production attempt.
