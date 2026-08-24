# Runtime baseline diff

Schema: `rpi5.runtime-diff.v2`

Review level: `attention`.
Semantic material changes: 38; semantic informational changes: 13.
Raw dynamic observations retained: sockets +34/-33; interfaces +15/-16/~0.

This is an offline metadata comparison. No host collection or mutation occurred. Differences are facts, not a causal diagnosis.

## docker_versions

- changed: 2.
## containers

- changed: 3.
- removed: 1.
## compose_projects

## networks

## systemd_state

## enabled_units

- added: 15.
## failed_units

## timers

- structural_changes: 8.
- temporal_changes: 11.
## sockets

- stable added: 5.
- stable removed: 4.
- dynamic high-port churn: attention; raw +34/-33; aggregate 33 -> 34.
## interfaces

- dynamic veth churn: attention; raw +15/-16/~0; aggregate 16 -> 15.
## limitations


Ports below 32768 remain exact material identities. High-numbered socket observations remain raw in JSON but are grouped; bucket emergence/disappearance or a per-bucket count delta above 2 is attention.
Dynamically named veth observations remain raw in JSON but are grouped by profile. Pure name rotation with an unchanged profile multiset is informational; count or profile changes are attention.
Timer structural changes are attention; next/last timestamp movement is informational.
