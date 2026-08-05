# V07 runtime baseline lineage findings

V07 validates the current tracked history as one complete baseline lineage.

## Current verified lineage

- Archive transitions: `1`.
- Root collection: `2026-08-04T22:52:46Z`.
- Root SHA-256: `db222c2d66962400eb3eb836f4327a66479c96aa44d00f5f16b8071a45591204`.
- Current head collection: `2026-08-05T09:44:02Z`.
- Current head SHA-256: `2db82cc46d840aced4e57431195c821ead8f916bf9adfb707f2ac60c3bf371bc`.
- Archived transition: `2026-08-04T22-52-46Z--db222c2d6696`.
- Review ID: `0e2a4688c55016fd93dbea814c8be39d`.

The archived old binding equals the byte-for-byte archived baseline. The transition head equals the exact canonical current JSON, and the tracked current Markdown equals the shared deterministic renderer output.

## Negative validation

Synthetic tests reject lineage gaps in SHA-256, collection UTC, or other binding metadata; cycles; reused review IDs; a final head that does not equal current; non-matching Markdown; unsafe output paths; and symlink output paths. Empty and multi-transition pure-chain cases are also tested.

## Safety

V07 reads tracked sanitized repository files only. It does not collect host data, invoke Docker or systemd, use `sudo`, change access, deploy, remediate, or modify the current baseline or archive.
