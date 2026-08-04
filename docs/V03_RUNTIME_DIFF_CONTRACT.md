# V03 offline runtime diff contract

V03 compares two already-sanitized, schema-valid V02B JSON baselines entirely offline. It does not collect host data, invoke runtime tools, deploy, alert, remediate, or infer causality.

`compare-runtime-baselines.py` validates both inputs, binds their SHA-256 and existing metadata into deterministic JSON and Markdown reports, and writes only private atomic outputs beneath ignored `evidence/` or `exports/`. Material inventory changes receive `attention`; version, timer timestamp, and limitation changes are `informational`. Input metadata is binding context, not runtime drift.

`verify-runtime-diff.py` validates report structure, deterministic Markdown rendering, output boundaries, and review-level semantics without reading original baselines. The tracked fixtures are synthetic and contain no real runtime inventory.
