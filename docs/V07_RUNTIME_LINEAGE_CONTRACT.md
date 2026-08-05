# V07 runtime baseline lineage contract

V07 verifies the complete tracked history formed by the V04 archive and the current V02B baseline. It is an offline integrity check and performs no collection, deployment, remediation, or runtime mutation.

## Required continuity

`verify-runtime-baseline-lineage.py` first requires the existing archive verifier to pass. It then checks every accepted transition as one ordered chain:

- the archived baseline binding exactly equals the transition `old` binding;
- the index SHA-256 and UTC values equal the transition bindings;
- each transition `old` binding exactly equals the previous transition `new` binding;
- collection UTC values increase strictly;
- review IDs are not reused;
- a baseline SHA-256 cannot reappear as a later head;
- the final transition `new` binding exactly equals the canonical tracked current baseline;
- the tracked current Markdown exactly equals the deterministic renderer output.

An empty archive is valid and treats the current baseline as a standalone root and head.

## Report

Optional outputs are written atomically only below ignored `evidence/` or `exports/` paths. The deterministic report schema is `rpi5.runtime-baseline-lineage.v1` and contains the root, exact current head, ordered transition bindings, and explicit successful checks.

The report contains only already-sanitized tracked metadata. It does not infer causality, safety, exposure, or runtime health.
