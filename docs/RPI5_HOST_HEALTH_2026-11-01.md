# RPi5 host health observation — 2026-11-01

Status: **DATED READ-ONLY/SANITIZED OBSERVATION**, with explicitly recorded separately authorized host fixes. This is **not** evidence of a deployment, live ChromaDB integration, or ongoing service health.

- Host: `rpi5`. Date: **2026-11-01**, Europe/Berlin (**CET, UTC+01:00**).
- Last CV verification: **11:15:09 CET** (10:15:09 UTC). Docker and memory samples were collected during the same morning session; their exact individual timestamps were not captured.
- Control-plane repository: `rozkalnsandris/RPi5_main`, `main` at observation: `26fcd6a166efdef4c2dbdd1bdf5beba33bfed2de`.
- Evidence method: narrowly scoped read-only systemd metadata and sanitized journal counts; `/proc`, `/sys`, Docker summary metadata; exact local file hashes; previously authorized offline MCP help execution. No secrets, raw logs, database records, application configurations, or container environments are included.
- **Source of truth separation:** GitHub establishes source state; local host observations establish only the stated point-in-time runtime facts. Do not infer deployment, future state, or functional integration from source or a one-time test.

## 1. CV statistics timeout — fixed on host, post-fix runs confirmed

| Field | 2026-11-01 observation |
| --- | --- |
| Symptom before fix | `docker images -q` in stats generator hit `subprocess.TimeoutExpired` at 10 s. |
| Canonical CV source | `rozkalnsandris/rozkalns-cv` main `84a8b35dbeff536fc50eac53bcac7cc954096749`, merged PR [#553](https://github.com/rozkalnsandris/rozkalns-cv/pull/553); script blob `52745f255c2f84201cd7ad60ad9000c0102cab0e`. |
| Authorized host change | One-line stats generator timeout `10 -> 30` seconds, atomic promotion; no restarts. |
| Host script edit | **09:08:27 CET**; installed script SHA-256 `1d78d3eaa57bbbd19a9ec5b40a73454a03792f8f3b69d9effed76fe0b68c2f27`; exact intended source blob was independently validated. |
| Last observed old timeout | **09:04:11 CET** (before edit). |
| Post-fix journal window | **09:09:00–11:15:09 CET**; **127 starts, 127 successful finishes, 0 failed-result messages, 0 timeout exceptions**. |
| Service snapshot | `rozkalns-cv-stats.service` last result `success`, exit status `0`; timer `active/waiting` (last trigger at 11:14 CET). |
| Assessment | **PASS for 127 scheduled executions within the observed window**; not a promise of future success. |

Counts are classified from the scoped `rozkalns-cv-stats.service` journal, not raw log excerpts. Do not add together multiple log lines that describe one failure. Monitor failed-result and timeout counts in subsequent windows.

## 2. Hermes / Chroma MCP — config fix and offline import test passed

| Field | 2026-11-01 observation |
| --- | --- |
| Original issue | `chroma-mcp 0.2.6` with `mcp 1.6.0` imports `eval_type_backport`, absent from cached Pydantic 2.14.x. |
| Cache observation | 119 cached Chroma MCP `uvx` environments: Pydantic 2.13.4: 35, 2.13.5: 22, 2.14.0: 5, 2.14.1: 43, 2.14.2: 14. **Cache inventory only**, not current process dependency proof. |
| Static compatibility | `eval_type_backport` exists in cached Pydantic 2.13.4/2.13.5; absent in 2.14.0/2.14.1/2.14.2. |
| Authorized config change | Only Chroma MCP `uvx` arguments set to `--with 'pydantic<2.14' chroma-mcp`. Private config contents never recorded. |
| Config provenance | SHA-256 before: `217a7536cc4d3e2915838f5b1e4ba8685b3a5bb40b8fc75b72f32dac0adbbb23`; after: `cdd9f830b7dcce256c82fb3e381fe9a555cebde29459e9a0a484622f14312da8`; mode `0600` preserved. |
| Promotion | Verified one-shot atomic file replacement; earlier staged/preflight attempts did not change the original file. |
| Offline startup smoke | **PASS**, exit `0`, package imports and CLI `--help` recognized; `uvx --offline` with narrowly scoped cache writes and no ChromaDB use. |
| Hermes gateway | `hermes-gateway.service` active/running, PID 952; service active since **2026-10-25 10:33:53 CET**. No restart/reload after configuration edit. |
| Outstanding | **Live gateway reinitialization and ChromaDB connection are NOT tested/authorized here**. Do not mark MCP live-ready based on offline `--help`. |

## 3. Memory and swap — no immediate OOM evidence

| Metric | 2026-11-01 observation |
| --- | ---: |
| RAM total | 4,049.8 MiB |
| RAM available (`MemAvailable`) | 1,357.2 MiB |
| RAM cached | 1,170.1 MiB |
| Swap total | 4,072.8 MiB |
| Swap used (derived) | ~1,612.4 MiB |
| zram swap used | ~1,583 MiB of 2,025 MiB |
| Non-zram swap used | ~29 MiB of 2,048 MiB |
| zram original data / compressed data / physical RAM use | 1,471.5 / 300.7 / 328.1 MiB |
| zram data compression ratio | 4.89x |
| `pswpin` / `pswpout` | +163 / +46 pages in a 6-second interval |
| `oom_kill` (kernel counter) | 0 as observed |
| Memory PSI | **unavailable** at `/proc/pressure/memory` and cgroup root; no pressure assessment possible from PSI |

Point-in-time largest examples: one container `python3` process ~382.0 MiB RSS / 253.9 MiB swap; Hermes gateway ~238.1 MiB RSS / 60.9 MiB swap. Swap occupancy alone is not memory pressure. No services restarted or memory limits modified.

## 4. Docker images, build cache, storage — no pruning

| Metric | 2026-11-01 observation |
| --- | ---: |
| Root/NVMe filesystem size | 234.3 GiB |
| Free filesystem space | 66.1 GiB |
| Filesystem used | 66.7% |
| Containers | 25 total: 21 running, 4 non-running |
| Images | 629 unique image IDs (637 formatted rows including duplicate references) |
| Images size / Docker-reported reclaimable | 62.9 GB / 46.09 GB (73%) |
| Images without a repository/tag (unique IDs) | 378 |
| Unique image age buckets | <7 days: 62; 7–29 days: 225; 30–89 days: 287; 90–179 days: 53; 180+ days: 2 |
| Build cache | 456 entries, 5.69 GB; reported reclaimable 4.114 GB |
| Local volumes | 10 total (9 active), 1.557 GB; reported reclaimable ~526.1 kB |
| Container writable layers | 74.94 MB; reported reclaimable ~36.86 kB |
| `docker image ls -a` read-only latency | 8.9–11.2 seconds across observed queries |
| `docker system df --format '{{json .}}'` latency | 22.0 seconds |

**No `docker image prune`, `docker builder prune`, `docker system prune`, volume deletion, or container mutation occurred.** Docker's reclaimable figures are not guaranteed freed space and do not account for operational rollback requirements. `image prune -a` can remove all images not associated with an existing container, including images reserved for rollback. The 4 stopped containers are part of the preservation assessment.

## 5. Read-only operator comparison protocol

Next sample: record an exact collection timestamp (UTC + local CET/CEST), current GitHub `main` SHA separately from host-deployed hashes, and gather the **same fields and units**. Compare:

1. CV stats: deployed script SHA, `timeout`, systemd last result, and matched **start/finish/failure/timeout counts with explicit time window**.
2. Hermes MCP: config fingerprint, sanitized Chroma-only args, gateway activation timestamp, and isolated offline test versus **separately authorized live connection**.
3. Memory: `MemAvailable`, zram logical/physical use, disk swap, page-in/out interval, OOM counter and PSI **availability**; preserve sampling duration.
4. Docker: disk free/used (GiB), container counts, unique images and untagged count, age buckets, image/cache/volume reclaimable (Docker **decimal GB**), metadata query latencies; do not automatically prune.

Record changes and confirmed failures separately from observations. Distinguish **source readiness**, **offline startup**, and **runtime readiness**. Do not inspect protected configs, secrets or raw logs; sanitize counts at the source. Any new host mutation, restart, Docker prune or live ChromaDB test requires its own scoped owner authorization.

## 6. Web documentation checked 2026-11-01

- [Docker: prune unused objects](https://docs.docker.com/engine/manage-resources/pruning) and [`docker image prune`](https://docs.docker.com/reference/cli/docker/image/prune): `-a` removes images not associated with any existing container; keep rollback risk separate from reclaimability.
- [Docker: `docker builder prune`](https://docs.docker.com/reference/cli/docker/builder/prune/): build-cache-specific cleanup, still a mutation requiring authorization.
- [uv: tool dependencies](https://docs.astral.sh/uv/concepts/tools/): `uvx --with` accepts a package specification; [`--offline`](https://docs.astral.sh/uv/reference/cli/) uses only locally available data.
- [Pydantic changelog](https://pydantic.dev/docs/validation/latest/get-started/changelog/): version 2.14 removes `eval_type_backport()`.
- [Linux kernel PSI documentation](https://docs.kernel.org/accounting/psi.html): PSI would provide memory stall trends; availability was not confirmed on this host.

## Decision / follow-up

- CV statistics: observed healthy after the focused timeout fix.
- Chroma MCP: **offline smoke PASS, live integration unverified**; no gateway restart.
- Memory: no observed OOM kills; insufficient PSI for firm pressure conclusion.
- Docker: storage not urgent (66.1 GiB free); retain rollback images and build cache pending a separate risk decision.
- This record is a **dated baseline for comparison**, not a permission to prune, restart, redeploy or merge.
