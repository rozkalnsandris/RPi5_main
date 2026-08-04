# V03 findings

V03 was developed from repository commit `8547c06c2913387c3ed55ed7ab8de3844e6f2208` and self-compared the authoritative `baselines/runtime/current.json` snapshot offline.

- Input SHA-256: `db222c2d66962400eb3eb836f4327a66479c96aa44d00f5f16b8071a45591204` for both sides.
- Existing input evidence binding: source commit `c1c176868db1baddbb92ab3dc05e09c8dece7015`; manifest SHA-256 `2a4689aeeddf58bcbe7a4a380cb1dc10f237e5466a47b83bf90fd384c4c2bf54`.
- Generated self-comparison report schema: `rpi5.runtime-diff.v1`.
- Direct result: zero added, removed, changed, material, and informational runtime changes; review level `none`.
- `verify-runtime-diff.py` returned PASS and the Markdown report states `No runtime drift detected`.

This proves deterministic operation against the current authoritative schema only. No second temporal baseline was available or collected, so it makes no temporal, host-health, or causal claim. V03 is ready to compare a future second verified V02B baseline without collecting or changing the host.
