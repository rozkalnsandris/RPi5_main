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

## V02B — complete: verified runtime baseline

V02B adds a bounded host-equivalent read-only runtime collector, verifier, renderer, and a sanitized tracked baseline bound to verified evidence. It does not change Docker access, permissions, services, or production configuration. See the [runtime baseline contract](V02B_RUNTIME_BASELINE_CONTRACT.md) and [current baseline](CURRENT_RUNTIME_BASELINE.md).

## Later phases

Each subsystem is imported separately with redaction, tests, rollback instructions and a pull request.
