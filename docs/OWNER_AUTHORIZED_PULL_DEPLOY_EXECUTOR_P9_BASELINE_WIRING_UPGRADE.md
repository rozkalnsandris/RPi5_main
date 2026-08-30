# P9 Control baseline post-install wiring upgrade

Status: **SOURCE ONLY / DORMANT / LIVE UPGRADE NOT AUTHORIZED BY MERGE**

## Purpose

The original reviewed P9 runtime installer from `RPi5_main@416860795831203e1670cb383c527bd212614a1d` was intentionally one-shot and fail-closed: it installed fresh P9 targets and refused any reinstall once those targets existed. PR #282 later added the Control baseline collector/operator wiring to source, so rerunning the fresh installer is not a valid upgrade path for a host that already contains the reviewed #281 runtime.

`scripts/install-deploy-executor-p9-baseline-wiring-upgrade.sh` is the narrow post-install upgrade path for that exact situation.

## Frozen accepted baseline

Before its first host mutation the upgrade must prove all of the following:

- the checkout HEAD equals the exact newly authorized `RPi5_main` SHA supplied by the owner;
- the upgrade source paths are byte-clean against that exact SHA;
- the existing P9 package/config/state/evidence roots and main P9 operator are present as non-symlink paths;
- the installed `p9_control_postcanary_producer.py` is root-owned mode `0644` and byte-for-byte matches the producer from the reviewed original runtime source `416860795831203e1670cb383c527bd212614a1d`;
- the new collector target and Control baseline operator target do not already exist.

Any mismatch is a pre-mutation STOP. The script does not attempt repair, cleanup, rollback or a second baseline interpretation.

## Authorized mutation surface

Once a separately explicit LIVE authorization is granted, the upgrade writes exactly three P9-specific targets:

1. add `p9_control_postcanary_collector.py` to the existing P9 package tree;
2. add `/usr/local/sbin/rozkalns-deploy-p9-control-baseline`;
3. replace the exact old reviewed `p9_control_postcanary_producer.py` with the newly reviewed producer.

It does not create or modify P9 config, StateStore, evidence directories, users/groups, systemd units/timers, GitHub App credentials, the future Control D1 token, GitHub App repository scope or permissions. It does not produce baseline evidence and does not run either P9 operator.

After the first of those three writes, any error or ambiguity is fail-closed STOP with no automatic retry/cleanup/rollback.

## Gates after source merge

Source merge only makes this upgrade reviewable/deployable. It does not authorize host mutation. A future host transaction must bind the then-current exact `RPi5_main/main` SHA and explicitly authorize this upgrade script on RPi5. Credential/permission changes, D1 access, baseline production and genuine P9 execution remain separate LIVE gates.
