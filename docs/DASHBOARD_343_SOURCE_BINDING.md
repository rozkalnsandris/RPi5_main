# Dashboard candidate 34336642 exact source binding

RPi5 source is bound to Dashboard application candidate `343366427441811a22739b05b04d069c10905805`, tree `76d69ef0fee15deceb26eb00a479e912312a241f`, parent `066b9a24008dd57439f9e66eae198416c4dfc590`, producer blob `bea0f30602d119ae53b81e70ce2d4c283d369ce8`, candidate SHA-256 `076db053e5dc83016168a1e6cecb291e063587c7a977fc3683c2b4bf9dc861db`, 72 files and 6,897,167 bytes.

The preverified handoff materializer and candidate stager remain `execution_enabled=false`; the trusted execution bundle is rebound to the exact modified wrapper/core Git blobs. Tests reject the old `066b9a24008dd57439f9e66eae198416c4dfc590` candidate and accept only the new immutable source-level binding.

This clears only the RPi5 **source prerequisite** corresponding to `RPI5_MAIN_DASHBOARD_343_EXACT_PROVENANCE_BINDING_NOT_SOURCE_READY` after merge. It does not prove current host state and does not authorize root staging, PLAN, APPLY, service/runtime changes or production deployment.
