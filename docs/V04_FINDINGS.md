# V04 findings

V04 was developed from repository commit `38823258db8edd62a7d7c6da283ed20335bcb2bd`.

Direct verified results:

- the shared Markdown renderer reproduces the tracked current baseline document byte-for-byte;
- canonical synthetic candidates produce deterministic `none`, `informational`, and `attention` reviews;
- `accepted`, `rejected`, and `deferred` decision boundaries are enforced;
- only an exact, strictly newer, reviewed candidate with an `accepted` decision is promotable;
- a synthetic accepted promotion archives the old JSON and Markdown byte-for-byte, updates the deterministic archive index, and passes the archive verifier;
- a deferred self-review of the tracked current baseline verifies and is refused by the promotion command;
- the tracked archive index is valid and empty;
- generated review bundles remain ignored and untracked.

The authoritative current JSON remains bound to SHA-256 `db222c2d66962400eb3eb836f4327a66479c96aa44d00f5f16b8071a45591204`. CI records and verifies the current Markdown SHA-256 and confirms both tracked files remain unchanged.

No second temporal V02B candidate was supplied, reviewed, accepted, or promoted. Therefore V04 makes no temporal-drift, runtime-health, or causal claim. No host collection, runtime command, privilege change, deployment, or production mutation occurred.
