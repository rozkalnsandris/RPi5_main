# V09 memory-pressure series findings

V09 was motivated by the first four-sample V08 idle series and an ad-hoc display bug that overstated container changes by 1024×.

## Verified idle-series interpretation

The four live V08 bundles from 2026-08-05 12:10–12:26 UTC each passed strict verification. Across the series:

- MemAvailable remained 39.59–40.39%;
- logical swap decreased by 20480 KiB;
- sampled totals were 8 swap-in pages, 0 swap-out pages, 73 major faults, 0 OOM kills and 0 PSI time;
- the correct series interpretation is `intermittent_activity`, not sustained pressure.

AdGuard moved from 436.1 MiB to 438.4 MiB. Normalizing each displayed value independently to whole KiB gives `446566 KiB` and `448922 KiB`; the resulting change is `2356 KiB`, rendered as `2.30 MiB`. The earlier terminal helper incorrectly treated bytes as KiB when rendering MiB and displayed approximately +2355 MiB.

## Root-cause status

The idle series does not demonstrate sustained host memory pressure or an AdGuard leak. AdGuard remains a large steady consumer near its 500 MiB limit and requires longer observation. The earlier controlled VS Code Remote/Codex shutdown remains the strongest evidence for the principal transient contributor to elevated RAM and swap.

## Safety

V09 reads verified ignored evidence only. It does not collect new host data, read process arguments or environments, access application configuration, use `sudo`, restart services, clear swap, tune zram, mutate Docker or change production state.
