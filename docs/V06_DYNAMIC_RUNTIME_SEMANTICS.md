# V06 dynamic runtime semantics contract

V06 refines the offline runtime-diff policy without changing V02B collection or the tracked baseline schema.

## Report compatibility

New comparisons emit `rpi5.runtime-diff.v2`. The verifier and archive tooling continue to accept and deterministically render archived `rpi5.runtime-diff.v1` reports. Existing archive files and checksums remain unchanged.

## Socket semantics

Every exact added or removed socket observation remains in the JSON report.

- Ports below `32768` remain stable exact identities and are material.
- Ports from `32768` through `65535` are retained under `dynamic_high_port`.
- High-port changes are grouped by protocol and address scope.
- Pure rotation or a count delta of at most two within an already-existing bucket is informational.
- A bucket appearing or disappearing, or a per-bucket count delta greater than two, is attention.

The grouping does not identify a process, exposure, vulnerability, or cause.

## Interface semantics

Every exact added, removed, or changed `veth` observation remains in the JSON report.

- Non-`veth` interfaces remain stable exact identities and are material.
- Names matching `^veth[0-9a-f]{7,15}$` are grouped by their sanitized interface profile.
- Name rotation with an unchanged profile multiset is informational.
- A profile or aggregate count change is attention.

## Counts

The v2 summary separates semantic change counts from raw dynamic observations. A dynamic group contributes one semantic change, while raw added/removed objects remain available for audit.

The comparison remains deterministic, offline, standard-library-only, and non-causal. It performs no host collection, monitoring, deployment, remediation, or runtime mutation.
