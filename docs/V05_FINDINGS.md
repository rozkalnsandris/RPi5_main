# V05 first reviewed runtime baseline refresh

V05 completed the first real temporal refresh through the existing V02B collection, V03 comparison, and V04 human-gated promotion workflow.

## Verified inputs and decision

- Development and collection source commit: `b1dd93d460ad71c1cf80502f7b2dc875fe384a1f`.
- Previous current baseline collection: `2026-08-04T22:52:46Z`.
- Previous current baseline SHA-256: `db222c2d66962400eb3eb836f4327a66479c96aa44d00f5f16b8071a45591204`.
- Candidate collection: `2026-08-05T09:44:02Z`.
- Candidate baseline SHA-256: `2db82cc46d840aced4e57431195c821ead8f916bf9adfb707f2ac60c3bf371bc`.
- Candidate evidence manifest SHA-256: `872adb99cf9fa9b5c18380b2f0d737f23acd593b4b718311410359042377fb73`.
- Review ID: `0e2a4688c55016fd93dbea814c8be39d`.
- Decision: `accepted`.
- Decision reason: `inventory_refresh`.
- Reviewer: `rozkalnsandris`.
- Decision UTC: `2026-08-05T09:48:50Z`.

The review was classified as `attention`: 102 material and 10 informational changes. Docker versions, containers, Compose projects, Docker networks, enabled units, failed units, and timer structure were unchanged. The material count came from one systemd state change, rotating high-numbered listening sockets, and replacement of dynamically named `veth` interfaces. Timer changes were temporal only. The systemd state changed from `degraded` to `running`, while failed units remained zero.

The decision records observed metadata only. It does not infer the cause, safety, or health impact of any change.

## Promotion result

The V04 promotion transaction:

- archived the previous JSON and Markdown byte-for-byte;
- archived the verified review, diff, decision, transition, and checksums;
- updated `baselines/runtime/archive/index.json`;
- promoted the exact reviewed candidate to `baselines/runtime/current.json`;
- deterministically rendered `docs/CURRENT_RUNTIME_BASELINE.md`;
- passed review verification, archive verification, the full validation suite, Python syntax checks, and the secret guard.

Archive entry:

`baselines/runtime/archive/2026-08-04T22-52-46Z--db222c2d6696/`

New current baseline SHA-256:

`2db82cc46d840aced4e57431195c821ead8f916bf9adfb707f2ac60c3bf371bc`

New current Markdown SHA-256:

`145c86d5e524837447d401a939043cbc1cd41ac623574193bf4401bebaa751a2`

## Safety and limitations

The host collection was read-only and ran as `andris` without `sudo`. No access control, service, container, network, package, database, backup, deployment, or production configuration change was performed. Raw evidence and working review artifacts remain ignored and untracked.

This is a comparison of two sanitized snapshots. It is not continuous monitoring or causal diagnosis.
