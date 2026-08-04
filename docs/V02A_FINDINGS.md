# V02A least-privilege access-model findings

## Verified collections

| Context | UTC | Source commit | Files / bytes | `SHA256SUMS` SHA-256 |
| --- | --- | --- | --- | --- |
| `codex-standard` | `2026-08-04T22:15:15Z` | `5eff5296e9b323885aa7f35fdf86726891b9ab73` | 32 / 10,015 | `addbb1e13da005f531f17b9a58acf7a15d0bb364cf3bbb5fd6a85e1dcb47020d` |
| `host-approved` | `2026-08-04T22:15:24Z` | `5eff5296e9b323885aa7f35fdf86726891b9ab73` | 32 / 26,524 | `1e29ac6d60081b15027712176aa2adec7248559ba8dd083c2b140ba8268af019` |

Both results passed `verify-access-diagnostic.sh`. A generated, ignored comparison artifact also passed its checksum verification.

## Direct facts

- `docker`, `systemctl`, `ss`, `ip`, `stat`, `namei`, `readlink`, `timeout`, and `python3` were present in both contexts with the same resolved binary paths.
- Docker socket metadata differed by context: standard Codex observed a socket mapped to `nobody:nogroup`; approved host context observed `root:docker`, mode `660`. In both contexts the current-user readable/writable and socket-group-membership booleans were `true`.
- In standard Codex, Docker server/version, container projection, network projection, and Compose projection were classified `permission_denied`. In approved host context, all four succeeded.
- In standard Codex, system-unit state, enabled-unit, failed-unit, and timer probes were classified `system_bus_unreachable`. In approved host context, the three listings succeeded; the high-level system-state probe returned `other_error`, not a bus-access classification.
- `ss -H -lntu` succeeded in both contexts. `ip -brief address` was `restricted_or_not_permitted` in standard Codex and succeeded in approved host context.
- The user, mount, PID, and network namespace identifiers differed between the two contexts.

## Facts versus inference

The classifications, socket metadata, group-membership booleans, command presence, and namespace identifiers above are direct evidence.

**Inference:** the contrast strongly supports `likely_execution_context_difference` rather than a missing Docker group membership or a disabled host daemon. This is not a claim that every host execution context is identical; it is limited to the two verified contexts. No host access change was applied or needed for the approved host-context probes.

## Decision and limitations

Final V02A decision: **`likely_execution_context_difference`**.

The standalone standard-context diagnostic selected `mixed`; the standalone host diagnostic selected `no_access_change_needed`. The final decision uses the verified comparison. V02A does not establish the reason for the host system-state probe's non-zero `other_error`, and it intentionally did not inspect raw unit data, service configuration, process state, or Compose files.

Generated evidence remains ignored and untracked. This document contains no raw errors, IP addresses, container data, configuration, or secrets.

## V02B recommendation — do not implement here

Do not add users to the `docker` group and do not introduce passwordless sudo. Prefer running future read-only inventory through a verified host-equivalent execution context when that is the stated task boundary. If a durable non-Codex path is genuinely required later, evaluate a narrowly scoped root-owned immutable helper with a fixed metadata allowlist, fixed output schema, validation, and no arbitrary arguments. A one-shot manually approved root collection is only an alternative for future consideration.
