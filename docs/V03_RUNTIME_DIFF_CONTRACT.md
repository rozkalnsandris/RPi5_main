# V03 offline runtime diff contract

V03 compares two already-sanitized, schema-valid V02B JSON baselines entirely offline. It does not collect host data, invoke runtime tools, deploy, alert, remediate, or infer causality.

`compare-runtime-baselines.py` validates both inputs, binds their SHA-256 and existing metadata into deterministic JSON and Markdown reports, and writes only private atomic outputs beneath ignored `evidence/` or `exports/`. Material inventory changes receive `attention`; version, timer timestamp, and limitation changes are `informational`. Input metadata is binding context, not runtime drift.

New comparisons use `rpi5.runtime-diff.v2`, whose dynamic socket and `veth` grouping rules are defined by the [V06 semantics contract](V06_DYNAMIC_RUNTIME_SEMANTICS.md). Exact raw observations remain in JSON. Archived `rpi5.runtime-diff.v1` reports remain supported and immutable.

`verify-runtime-diff.py` validates report structure, deterministic Markdown rendering, internal semantic counts, dynamic-group classifications, output boundaries, and review-level semantics without reading original baselines. The tracked fixtures are synthetic and contain no real runtime inventory.
