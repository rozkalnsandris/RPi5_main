# Home Assistant container resource envelope

Issue: #474.

## Desired state

`homeassistant` is bounded to:

- `mem_limit: 768m`
- `mem_reservation: 350m`
- `memswap_limit: 1g`

In Docker Compose, `mem_limit` is the container memory limit and `memswap_limit`
is the combined memory-plus-swap limit. The desired envelope therefore permits
768 MiB RAM and approximately 256 MiB additional swap while preserving the
existing 350 MiB reservation.

## Why this is source-managed

The runtime audit found an effective working set above the previous 500 MiB RAM
cap, with no OOM but material swap use and repeated `memory.max` pressure. A
separately authorized runtime-only correction changed the live container without
restart or recreate. The existing Compose override is not Git-managed, so a
future Compose recreate can otherwise restore the stale 500 MiB value.

The JSON contract in `ops/contracts/homeassistant-container-resource-envelope.json`
is the canonical desired resource envelope. The capability-specific operator
`ops/bin/homeassistant-compose-resource-envelope` only plans or materializes
those three resource keys in an explicitly supplied Compose override.

## PLAN

PLAN is read-only:

```text
ops/bin/homeassistant-compose-resource-envelope \
  --contract ops/contracts/homeassistant-container-resource-envelope.json \
  --target <compose-override> plan
```

The output contains only status, service name, input SHA-256, and allowlisted
resource-key names. It does not print unrelated Compose content.

## APPLY boundary

APPLY is a host mutation and requires a separate explicit LIVE authorization.
It must receive the exact target SHA-256 observed during the authorized
preflight, the complete ordered Compose file set, and the project directory.
Before writing, the operator renders a candidate in the target directory and
requires `docker compose ... config --quiet` to accept that candidate. It then
revalidates the target SHA immediately before one atomic replace.

APPLY does not run `docker compose up`, restart/recreate a container, upgrade an
image, or modify Home Assistant configuration. Runtime convergence after the
Compose source patch is a separate owner-gated action if it is ever required.

Any SHA drift, ambiguous/missing service, duplicate allowlisted key, candidate
validation failure, or other error fails closed before the target write.
