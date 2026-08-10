# V26 maintenance APT check contract

## Purpose

Issue #138 corrects the maintenance updater's `--check` contract. The previous V25 source ran `apt-get update` before package simulations even in check mode. That refreshed `/var/lib/apt/lists` metadata, so the mode was not strictly non-mutating even though it did not install or remove packages.

Debian Bookworm's `apt-get(8)` contract distinguishes these operations:

- `update` resynchronizes package index files from configured sources;
- `-s` / `--simulate` performs a no-action simulation based on current system state.

V26 therefore separates metadata acquisition from simulation rather than describing both as one dry-run path.

## Mode contract

### `run`

- refresh APT repository metadata first;
- fail the APT phase if metadata refresh fails;
- run the existing no-removal `upgrade --with-new-pkgs --no-remove` simulation;
- keep `full-upgrade` simulation as manual-review evidence only;
- perform the existing guarded package apply only after the refreshed simulations pass.

### `check`

- MUST NOT invoke `apt-get update`;
- MUST NOT acquire the shared maintenance mutation lock;
- use the already-present APT lists/cache for `apt-get -s` simulations;
- report that cached metadata is being used;
- report a bounded local list-mtime age indicator when it can be derived;
- warn when cache freshness cannot be established;
- treat the local list-file mtime as an indicator only, not as proof of the last successful repository refresh;
- keep incomplete `dpkg --audit` state non-mutating and visible as a warning/failure exactly as before.

### `cleanup-only`

Unchanged by #138. It exits through the existing bounded cleanup path before the APT update/simulation phase.

## Fail-closed implementation boundary

`ops/lib/rpi5-update-apt-policy.sh` owns the metadata-refresh decision. `rpi5_prepare_apt_metadata` accepts exactly:

- `run`: invoke `apt-get ... --error-on=any update`;
- `check`: return the explicit metadata-skipped status without invoking `apt-get`;
- anything else: reject the request.

The updater delegates metadata preparation to this helper, while the source validator rejects a direct `--error-on=any update` command in `ops/bin/rpi5-update`. The focused regression test stubs `apt-get` and proves that check/invalid modes make zero metadata-refresh calls while run mode makes exactly one reviewed refresh call.

## Freshness evidence

A no-refresh check cannot authoritatively prove when every configured repository was last successfully synchronized. V26 therefore does not fabricate a precise `apt-get update` timestamp. When available it reports the age of the newest regular file under `/var/lib/apt/lists` as a local cache indicator and explicitly labels that value as non-authoritative. If no usable list-file mtime is available, it emits a freshness warning and continues with cached simulation; the simulation itself still fails normally if APT cannot use the cache.

## Production boundary

This repository change does not install V26 on the RPi5 and does not authorize an updater execution. The currently installed V25 SHA remains authoritative until a separate exact-source host activation is explicitly approved after merge.

A production activation must bind the merged V26 source/helper identities, preserve the existing shared-maintenance-lock and notifier boundaries, install only the reviewed files, and verify `--check` behavior without running a real weekly update merely as a smoke test.
