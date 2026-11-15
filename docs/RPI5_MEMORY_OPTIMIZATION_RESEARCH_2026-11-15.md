# RPi5 4 GiB: memory optimization research and measurement plan

Status: **SOURCE-ONLY PRELIMINARY RESEARCH** (2026-11-15). Issue: [#1469](https://github.com/rozkalnsandris/RPi5_main/issues/1469); baseline dependency: [#1468](https://github.com/rozkalnsandris/RPi5_main/issues/1468). This is not a production tuning recommendation or LIVE authorization.

## Current evidence and constraints

- Actual 2026-11-15 observation: Raspberry Pi 5 Model B with 4 GiB RAM, Raspberry Pi OS 64-bit based on Debian 12 Bookworm, kernel `6.12.115+rpt-rpi-2712`, NVMe ext4 root; `/etc/rpi-issue` identifies a `pi-gen` **stage2** image. Upstream `pi-gen` defines stage2 as **Raspberry Pi OS Lite**, so re-installing another Lite image does not by itself remove a desktop that is already absent.
- Prior 2026-11-15 V08: four independently verified bundles and a PASS V09 series, over **09:06:58–09:08:56 UTC**. Sanitized outcome is recorded in [#1468 comment](https://github.com/rozkalnsandris/RPi5_main/issues/1468#issuecomment-6892160542). Original V09 classified `sustained_pressure` because **3/4 short windows showed swap-out**, not because of OOM, low MemAvailable or valid PSI observations.
- Across those windows, **MemAvailable 37.99%–39.39%**, swap occupancy **1744.89 → 1727.89 MiB** (−17 MiB), **434 swap-in / 539 swap-out pages**, **503 major faults** and **0 OOM**. These are short, not load-matched windows and do **not** establish severe thrashing or a memory leak.
- `/proc/pressure/memory` was **unavailable** in all four bundles. The old V08/V09 release displayed synthetic PSI zeroes; PR [#1470](https://github.com/rozkalnsandris/RPi5_main/pull/1470) corrected **source-level** unknown/available semantics. **Do not mutate historical evidence**, mistake historical PSI zeroes for measurements, or infer that the corrected tools have been installed on the host.
- Current `zram` is **already enabled**, with about **1.48 GiB** logical stored data compressed to approximately **326 MiB** of allocated RAM during the earlier direct sample. This virtual capacity is not free physical RAM and is not additive to `MemAvailable`. A smaller non-zram swap area was also in use. zram settings should remain unchanged until comparative pressure/cost data exist.
- One 4-sample Docker CLI working-set series reported **Grafana up to 263.2/300 MiB (87.72% of limit)**, Home Assistant **367.5/768 MiB**, Uptime Kuma **142.8/200 MiB**, AdGuard **148.1/500 MiB**, and Prometheus **75.61/100 MiB**. Those are samples, not peaks, PSS, private/exclusive RAM or proof of leaks. Docker CLI subtracts certain page-cache usage on Linux; do not add these values as a host total.
- Historical [V09](V09_FINDINGS.md), [V11](V11_FINDINGS.md) and [Home Assistant envelope](HOMEASSISTANT_CONTAINER_RESOURCE_ENVELOPE.md) findings establish prior behavior/limits but cannot certify current host state. Keep Home Assistant's already-reviewed memory envelope; never blindly lower limits.

## Priority comparison — hypotheses, not measured savings

| Priority | Candidate | Why investigate | Potential RAM benefit | Risk / rejection gate |
| --- | --- | --- | --- | --- |
| 1 | **Attribute Grafana/monitoring working set and limit headroom** | Grafana measured at 87.72% of its 300 MiB cap; Prometheus and Uptime Kuma are also material consumers | **Unknown** until comparable workload and PSS/cgroup peak data; a lower cap alone saves no RAM | Monitoring/alerts/renderers must remain reliable; reject any limit leading to OOM, increased tail latency or data loss |
| 2 | **Attribute host-side Python, containerd and Hermes process RAM** | A point-in-time host `ps` reading showed `python3` ~357 MiB RSS, `containerd` ~292 MiB RSS and `hermes` ~235 MiB RSS | **Unknown**; RSS is not PSS and may double-count shared pages | Determine ownership and safety of each process without reading process args, environments, protected app state or killing processes |
| 3 | **Review development/preview workload necessity and idle costs** | Preview/UI-dev containers were visible in the one-time 21-container snapshot | **Unknown**; several individual sampled usages were only a few to tens of MiB | No auto-stop/recreate; first prove owner, purpose, dependencies and recreation policy |
| 4 | **Compare existing zram + NVMe swap behavior** | Repeated small-window swap-out despite substantial MemAvailable | **Unknown**; compression already effective | CPU and thermal overhead, IO latency, tail latency, OOM and possible NVMe wear; do not clear swap or change swappiness |
| 5 | **Separate Trixie Lite test image** | Newer distro may bring lifecycle/compatibility/security improvements | **No justified RAM estimate**; current OS is already Lite and has a relatively new Raspberry Pi kernel | New boot medium, compatible Docker/Compose/systemd/kernel/firmware/network and rollback; never in-place upgrade production |

**Provisional decision:** keep existing Bookworm Lite and zram; measure before selecting a change. An OS replacement is **not** an optimization candidate without reproducible A/B evidence.

## Measurement and decision procedure

1. **Do not reuse the consumed 2026-11-15 LIVE authorization.** Any new host evidence-bundle writing, privileged/protected inspection, Docker configuration edit, restart, OS installation or deployment requires the respective current and exact owner authorization. GitHub/source-only research and tests require none.
2. Before additional diagnostics, prove the **exact installed** V08/V09 source version and provenance separately from `main`. Correct handling of missing PSI is required. Preserve the four original V08/V09 bundles and checksums unchanged; reanalysis with new tooling, if separately authorized, must write **new** output targets.
3. Sample multiple representative **idle** and **busy** periods with timestamps, workload labels and service-health readbacks, not four adjacent 5-second windows. Predeclare count, duration, collection tool, allowed metadata, storage and a sanitized/verifiable evidence contract.
4. Collect allowlisted `MemAvailable`, zram original/compressed/allocated bytes, total/active swap and **deltas** of `pswpin`, `pswpout`, `pgmajfault`, OOM, plus PSI **availability** (unknown if absent). Collect top process RSS/PSS and cgroup working set/peak/event counts only where access is explicitly permitted. Keep the source's known limitations visible.
5. Compare per-container **working set and limit headroom**, not just totals. Collect operational signals for Grafana and monitoring (dashboard/alert readiness and latency), DNS, Home Assistant, Hermes and host CPU/temperature. Flag a test invalid if workload, sampling windows, host image or relevant config are not comparable.
6. For each possible change, use **one** independently reviewable source-level candidate and an owner-authorized small canary with preflight, exact hash and health baseline. Stop on any new OOM, DNS/HA/Hermes/monitoring health regression, worsening service latency or identity drift; no assumed rollback or retry authority.
7. Report **measured before/after distributions** (typical and peaks; at minimum MemAvailable, swap rate, OOM, container peaks, service tail latency and CPU/temperature). Do not claim savings from reduced virtual swap capacity, Docker limit changes alone or cached pages.

## Explicit no-go actions in this phase

No process termination; no Docker inspect/environment/protected config; no changing `mem_limit`, `memswap_limit`, kernel, `zram`, `swappiness`, `/tmp`, service configuration or timers; no pruning, image replacement, secrets, database access, migration, restarts or production deploy. A source merge is **not** LIVE authorization.

## Authoritative references

- [Raspberry Pi `pi-gen`: stage2 builds Raspberry Pi OS Lite](https://github.com/RPi-Distro/pi-gen/blob/master/README.md).
- [Docker memory constraints, swap semantics and OOM warnings](https://docs.docker.com/engine/containers/resource_constraints/).
- [Docker CLI stats and Linux page-cache subtraction](https://docs.docker.com/reference/cli/docker/container/stats/).
- [Linux kernel `zram` memory statistics (`orig_data_size`, `compr_data_size`, `mem_used_total`)](https://docs.kernel.org/6.12/admin-guide/blockdev/zram.html).
- [Linux kernel pressure stall information (PSI)](https://docs.kernel.org/accounting/psi.html).
- [Raspberry Pi OS: major version upgrades should use a new image](https://www.raspberrypi.com/documentation/computers/os.html).

## Remaining gates for #1469

This research completes the **source-only comparison and A/B test design**, not the evidence-dependent tuning decision. #1468 still requires longer load-matched verified idle/busy observation and attribution of high consumers. Once collected, update this decision with measured RAM savings and a separate smallest safe optimization candidate. No invented performance result or claim of host readiness is permitted.
