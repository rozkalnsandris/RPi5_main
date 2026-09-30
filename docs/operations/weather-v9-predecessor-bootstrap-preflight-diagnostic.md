# Weather v9 predecessor-bootstrap privacy-safe preflight diagnostic

Issue: #636

## Purpose

Use this source-reviewed helper only after the installed Weather v9 predecessor-bootstrap broker has returned the bounded generic `FAIL_CLOSED` receipt and fresh evidence is needed to classify the read-only preflight failure without exposing protected runtime details.

The helper is diagnostic only. It does not replace or modify the installed bootstrap broker, registration, replay state, systemd, Weather runtime, database, corpus, permissions, network, or secrets.

## Output contract

The entrypoint is:

`python3 scripts/diagnose-weather-v9-predecessor-bootstrap-preflight.py`

It requires root only because canonical preflight metadata is below root-owned `0700` boundaries. Execution as root is a later, separate owner gate; source merge never authorizes it.

Output is one bounded JSON object. Failure output contains only the fixed `failure_stage` and `failure_code` enum declared in `ops/recovery/weather_v9-predecessor-bootstrap-preflight-diagnostic.contract.json`. Raw exception text, arbitrary paths, file contents, Git stderr, environment values and credentials are never returned.

The diagnostic checks, in order:

1. exact trusted source identity;
2. installed predecessor-bootstrap capability closure;
3. predecessor recovery contract;
4. bounded durable-state baseline metadata;
5. execution provenance;
6. predecessor artifact identity;
7. the canonical predecessor `preflight()` postcondition.

Any unexpected exception collapses to `INTERNAL / UNCLASSIFIED`.

## Later owner gate

After this source change is merged and exact-main CI is green:

1. materialize the exact merged `RPi5_main` SHA in a new clean detached trusted diagnostic checkout under a separate bounded source-delivery authorization;
2. verify that checkout identity read-only;
3. obtain a separate owner authorization for one root read-only diagnostic invocation;
4. run the diagnostic exactly once;
5. use only its bounded enum result to choose the next source/recovery lane.

No broker retry, predecessor-bootstrap apply, systemd reset/restart, cleanup, rollback, Weather runtime mutation or DB/corpus mutation is authorized by this document.
