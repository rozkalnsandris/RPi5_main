# Weather v7 home-access / LIVE-AUTH provenance repair (#595)

Status: SOURCE-ONLY / LIVE REPAIR NOT AUTHORIZED

This document is the canonical source recovery handoff for `RPi5_main#595`. It repairs the Gate-3 broker home-access boundary and the LIVE-AUTH provenance check without granting broader root/DAC authority or authorizing Weather deployment.

## Proven failure

The Weather-v7 broker is intentionally root-owned, but its systemd capability bounding set does not include DAC bypass. The canonical manager checkout is user-owned under `/home/andris/RPi5_main`, while the parent home is mode `0700`. A root process without `CAP_DAC_OVERRIDE` therefore cannot safely traverse the manager home merely because its effective UID is zero.

The previous `safe.directory=<exact manager>` repair solved Git's repository-ownership trust rule, but it did not solve Unix path traversal. `safe.directory` must remain exact and command-scoped; it is not a filesystem-permission bypass.

A second defect is authorization provenance. GitHub may report the configured owner as the issue `user` while also reporting `performed_via_github_app != null`. The canonical owner-authorization contract requires a directly owner-authored LIVE-AUTH, so app-mediated issue creation must fail closed.

## Correct privilege model

The repaired broker remains `User=root` only because the final operator target is root-owned. It receives exactly `CAP_SETUID` and `CAP_SETGID`; it does **not** receive `CAP_DAC_OVERRIDE` or `CAP_DAC_READ_SEARCH`.

All Git and home-access subprocesses are launched with the registration-bound manager identity:

- `user=<manager_uid>`;
- `group=<manager_gid>`;
- `extra_groups=()`;
- fixed minimal environment;
- exact `git -c safe.directory=<canonical manager> ...` trust;
- no wildcard/global/system Git configuration.

Python's POSIX `subprocess` contract explicitly supports `user=`, `group=` and `extra_groups=`. The Python documentation also notes that setting only `user=` does not drop supplementary groups, which is why this repair requires `extra_groups=()`.

The broker does not execute an upgrade script from the user home. The manager-identity Git child verifies the fixed reviewed source blob identities and returns the exact operator bytes. The root broker then performs only the single fixed atomic replacement of `/usr/local/sbin/rozkalns-weather-public-runtime-operator` already present in the Gate-3 1+1+1 mutation budget.

## Registration v2

`rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-registration.v2` adds:

- `manager_uid`;
- `manager_gid`.

Both are captured from the canonical manager checkout during trusted installation/repair and validated as strict non-root numeric identities. The caller cannot select a user, group, path, argv, command or environment.

## systemd sandbox

The broker service keeps `NoNewPrivileges=true` and `ProtectHome=read-only`.

Its capability bounding set is exactly:

```text
CAP_SETUID CAP_SETGID
```

`CAP_DAC_OVERRIDE` and `CAP_DAC_READ_SEARCH` remain absent. The broad `ReadWritePaths=/home` exception is removed; the only home write exception is the reviewed `/home/andris` subtree needed by the manager-owned Git child for the fixed sibling worktree.

## LIVE-AUTH provenance

The shared authorization parser now rejects any otherwise-valid LIVE-AUTH when:

```text
performed_via_github_app != null
```

That check is shared by both the identity-only caller and the privileged broker. Numeric owner identity, TTL, request UUID, exact queue binding, exact source SHA/CI, predecessor identity and the fixed 1+1+1 budget remain mandatory.

Historical app-mediated or failed request identities are not repaired or reused.

## Bounded installed-capability repair

The v2 repair contract is `ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-repair-v2.json` and the read-only/default entrypoint is `scripts/repair-weather-operator-v7-host-capability-home-access.py`.

After a dedicated trusted exact-main source checkout and a separately authorized root preflight, the repair may replace only:

1. `weather_operator_upgrade_v7_host_capability.py`;
2. `rozkalns-weather-operator-v7-privileged-broker`;
3. `rozkalns-weather-operator-v7-privileged-broker@.service`;
4. `registration.json` with schema v2;
5. one `systemctl daemon-reload`.

It does not restart the broker socket or caller timer, replace the Weather operator, create the v7 operator checkout, deploy Weather, mutate Docker/SQLite/corpus/network/Cloudflare, change credentials/secrets/permissions, retry, clean up or roll back automatically.

## Recovery order

1. Merge the reviewed `RPi5_main#595` source and require successful exact-main CI.
2. Materialize the dedicated repair-v2 source checkout under a separate bounded owner LIVE gate.
3. Run the repair entrypoint in read-only mode and prove the exact `99c5568...` installed predecessor closure.
4. Under a separate exact owner LIVE repair authorization, replace only the four fixed files and run one `daemon-reload`.
5. Verify registration v2, exact broker/module/service hashes, unchanged socket/caller state, predecessor operator, absent v7 checkout and preserved v6 checkout.
6. JIT reconcile `ops-workflows#63` to the then-current exact `RPi5_main/main`.
7. Create a brand-new **directly owner-authored** Weather-v7 LIVE-AUTH in GitHub; `performed_via_github_app` must be null.
8. Allow the existing timer/caller to submit it once.
9. Verify the exact v7 operator closure.
10. Return to `rozkalns_weather#136` Phase B and then the final bounded first-public Weather rollout.

## Design references

- Python `subprocess`: <https://docs.python.org/3/library/subprocess.html>
- Git `safe.directory`: <https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory>
- systemd execution sandboxing: <https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html>

These references support the mechanism only; repository-local contracts remain stricter and authoritative for this deployment path.

## Fail-closed rule

Source merge grants no LIVE authority. Each later host mutation requires its own exact owner gate. Once an authorized mutation begins, any error, drift or ambiguity permits only minimum-sufficient read-only evidence and STOP. No retry, rollback, cleanup, alternate privileged transport or capability widening is implied.
