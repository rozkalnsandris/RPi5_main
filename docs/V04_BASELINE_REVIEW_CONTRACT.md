# V04 controlled runtime baseline review contract

V04 is a strictly offline, manual, review-gated workflow for a second already-sanitized V02B baseline. It performs no host collection, runtime command, deployment, remediation, or automatic acceptance.

## Review

`prepare-runtime-baseline-review.py` canonical-validates the exact current and candidate JSON files, computes their SHA-256 bindings, produces a deterministic V03 diff, and writes a private immutable review bundle below ignored `evidence/` or `exports/`.

`verify-runtime-baseline-review.py` validates the bundle tree, checksums, review schema, V03 report, cross-bindings, and optional decision without requiring the original baseline files.

## Human decision

`record-runtime-baseline-decision.py` records exactly one decision:

- `accepted` permits a future promotion only when the candidate is strictly newer and differs from current;
- `rejected` is never promotable;
- `deferred` is never promotable.

The decision binds the reviewer, explicit UTC decision time, reason code, review ID, baseline digests, diff digests, and review level. No free-form notes are accepted.

## Promotion and archive

`apply-runtime-baseline-promotion.py` requires the exact expected current digest, exact reviewed candidate digest, a verified `accepted` decision, a strictly newer collection timestamp, and a valid archive index. It archives the previous JSON/Markdown plus review, diff, decision, transition, and checksums before replacing current through a rollback-safe transaction.

`verify-runtime-baseline-archive.py` validates the deterministic index and every archive entry. Direct automatic restoration is not implemented. Repository rollback remains `git revert`; an intentional chronology exception requires a separately scoped and reviewed future version.

The V04 implementation itself leaves the real current baseline and Markdown unchanged.
