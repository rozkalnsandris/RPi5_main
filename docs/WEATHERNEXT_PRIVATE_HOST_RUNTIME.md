# WeatherNext private host runtime composition

Status: **SOURCE READY / ONE-TIME HOST INSTALL REQUIRED**  
Issue: `RPi5_main#552`  
Host capability: `rpi5.weathernext-private-backend.v1`

## Outcome

This source slice closes the final host-installability gap after `RPi5_main#549` / PR `#551`. It does not install or activate the capability on `rpi5` and does not authorize Google, BigQuery, credential, Analytics Hub, SQLite, Docker, systemd, network or other production mutation.

The implementation provides:

- a concrete capability-specific `CanonicalPrivateFactsProvider`;
- fixed WeatherNext-private adapters over the merged execution bridge and trusted backend;
- one source-tree one-shot operator whose only caller input is `authorization_issue_number`;
- a deterministic later host install/activation contract for `rpi5.weathernext-private-backend.v1`;
- fixture/security tests and focused exact-head CI.

`ops/deploy/executor-operations.json` is intentionally unchanged while PR `#545` owns that shared registry. Weather public-v7 delivery files are also outside this lane.

## Canonical evidence boundary

The concrete facts provider derives only the closed facts required by the merged #549 contract:

- owner authorization issue identity and active authorization state from the reviewed private authorization surface;
- exact current `RPi5_main` SHA and required CI;
- exact reviewed `rozkalns_weather` SHA and required CI;
- exact private bridge operation, first-access contract and target `rpi5`;
- sanitized installed host capability, staged Weather source, reviewed private runtime and auth/project/link readiness states.

The conversational caller cannot provide source SHAs, target, command, path, argv, environment, account, project, dataset, credential or query selectors. Private Google identifiers are not part of the canonical facts or GitHub evidence.

A present private runtime must be the reviewed `cp313` runtime. System Python 3.11 cannot substitute for an absent reviewed runtime. Binding states are only `absent`, `ready` or `mismatch`; `mismatch` fails closed.

## Runtime-only protected bindings

The runtime composition keeps three private Google bindings distinct:

- `weathernext-private-google-auth-v1`;
- `weathernext-private-google-project-v1`;
- `weathernext-private-approved-linked-dataset-v1`.

Public-safe marker files expose only `absent` / `ready` / `mismatch`. The private first-access binding is read only after the durable one-shot owner authorization has been consumed. It may contain the fixed project/dataset identity and one **basename-only** credential-file reference under:

`/var/lib/rpi5-deploy/weather-private-bindings/credentials`

The credential file itself is bounded and must be mode `0600`. The provider uses explicit credentials loaded from that fixed reference. Ambient ADC and `GOOGLE_APPLICATION_CREDENTIALS` are not accepted as substitutes.

Missing Weather application staging, Google auth binding, project binding or Analytics Hub linked-dataset readiness does not cause this capability to invent or widen authority. The corresponding adapter fails closed and requires its separate exact later LIVE gate.

The read-only first-access adapter requires:

- exact staged Weather source;
- reviewed private `cp313` runtime;
- all three fixed binding slots ready;
- WeatherNext 3 model contract `3.0.0`;
- logical location `station_10416`;
- exactly six forecast hours;
- both required product surfaces;
- a fresh mandatory dry-run with source hard ceiling `<= 1 GiB/query`;
- the smallest defensible real-query cap derived from the fresh dry-run;
- the existing reviewed `rozkalns_weather.weathernext_access.read_first_access_canary` implementation;
- home scope disabled and SQLite writes disabled.

No raw WeatherNext values or private Google identifiers are emitted to GitHub. DWD remains the authoritative severe-weather warning source in Germany. WeatherNext remains `primary_research` forecast output.

## One-time host install contract

The later install target is `rpi5-weathernext-private-backend-install`. The frozen install mutation budget is exactly:

1. `git.weathernext-private-host-checkout-fetch` — max 1;
2. `git.weathernext-private-host-checkout-worktree-add` — max 1;
3. `filesystem.weathernext-private-host-operator-install` — max 1;
4. `filesystem.weathernext-private-host-activation-marker-write` — max 1.

Fixed targets are:

- trusted source checkout: `/var/lib/rpi5-deploy/RPi5_main-weathernext-private-host-trusted`;
- installed operator: `/usr/local/sbin/rpi5-weathernext-private-host`;
- activation marker: `/var/lib/rpi5-deploy/weather-private-host/capability.json`.

The trusted checkout and installed operator are root-owned mode `0755`; the activation marker is root-owned mode `0644`. The later installer must bind the package to one exact merged `RPi5_main` SHA, install only the reviewed source-file set, require no-follow and no-overwrite-or-exact semantics, and perform deterministic read-only verification of the exact resulting identity.

Rollback policy is `NONE`. Future LIVE authorization is consumed immediately before its first authorized mutation. After mutation begins, any source/head/CI/baseline drift, filesystem conflict, protected binding ambiguity, API/provider failure or health regression permits only minimum sanitized read-only evidence followed by STOP. There is no automatic retry, cleanup, rollback, credential substitution or alternate account/project/dataset/link.

This issue performs none of those host-install mutations.

## Post-merge gate order

After #552 source merge and exact-main verification, the order is:

1. one bounded owner-gated `rpi5` host capability install/activation for `rpi5.weathernext-private-backend.v1`;
2. sanitized read-only verification that the capability identity is exact;
3. separately frozen application staging/runtime/auth/project/link prerequisites only where absent;
4. `rozkalns_weather#122` read-only first access;
5. SQLite forecast snapshot write remains a separate later mutation gate.

Source merge does not authorize LIVE and does not make `rozkalns_weather#122` executable by itself.
