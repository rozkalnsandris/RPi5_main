# Roadmap

## V01 — safe inventory foundation

Create a strictly read-only collector that records only approved metadata:

- OS, kernel and architecture
- filesystem and block-device summary
- enabled systemd unit names
- systemd timer names and schedules
- Docker container names, images, states and health only
- Docker Compose project names only
- listening TCP/UDP ports without process environments
- package inventory
- failed systemd unit names
- basic backup job presence without backup contents

The collector must not read environment variables, container inspect environments,
credentials, database contents, private keys, raw Cloudflare configuration or Docker volumes.

## V02A — complete: least-privilege access-model diagnostic

V02A added a bounded diagnostic and verified standard/approved-context comparison for Docker, systemd, socket, and interface metadata access. It made no host changes. See [V02A findings](V02A_FINDINGS.md).

## V02B — future, not implemented

Evaluate only a narrowly scoped read-only collection path if a future task demonstrates a need outside the verified host-equivalent context. Do not automate Docker-group membership or passwordless sudo.

## Later phases

Each subsystem is imported separately with redaction, tests, rollback instructions and a pull request.
