# Ausmalwiese erroneous alphabet N-R batch hide

Scope: unlist exactly these five catalogue activities and their sitemap detail URLs:

- 5008429 — N - Nashorn und Nuss — alphabet
- 3559941 — O - Orange und Ofen — alphabet
- 3255194 — P - Pinguin und Pilz — alphabet
- 0363214 — Q - Qualle und Quadrat — alphabet
- 7403304 — R - Raupe und Regenbogen — alphabet

This is an unlisting operation only. It does not delete or overwrite media,
originals, inbox files, receipts, Drive files, analytics or engagement data.

Source operator:
`ops/bin/ausmalwiese-catalog-hide-alphabet-nr-20261021`

First-install-only installer:
`scripts/install-ausmalwiese-catalog-hide-alphabet-nr-20261021.py`

The operator requires an exact read-only `--check` first. `--apply` requires
the exact current catalog and sitemap SHA-256 values returned by that check.
It holds the existing Drive-ingest lock, validates all five exact
ID/title/category bindings and complete catalog↔sitemap consistency, stages
both candidates before replacing either public file, replaces sitemap first and
catalog second, then proves local HTTP bytes match.

Source merge grants no LIVE authority. Installation and the final LIVE apply
remain separate owner-authorized gates. After the first LIVE mutation, any
error is STOP: no retry, rollback, cleanup, alternate mutation path or media
deletion.
