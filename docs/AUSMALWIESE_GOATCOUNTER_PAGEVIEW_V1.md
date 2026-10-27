# Ausmalwiese GoatCounter pageview adapter + v2.7.0 proof (#1224)

**SOURCE ONLY. NOT INSTALLED. NO LIVE TRAFFIC COLLECTION.**

Frozen activation: `AUTO-RUN FULL RPi5_main #1224` from
`main=391a88cf805c9d69ca2e12b86ccf6168cd0f4b9d`.
The activation receipt is issue comment `6398544792`.

Cross-repo dependency: `coloring-pages` PR #391 at
`982e0659793d7257514f7c327a8d985f34b6a6fa` remains under **MERGE HOLD**.
This RPi5 source does not remove that hold and does not authorize any
`coloring-pages` merge or auto-LIVE flow.

## Architecture

Future data flow, after separate runtime and ingress authorization:

```text
browser
  POST https://ausmalwiese.de/api/pageview
  {"page_id":"1234567"}
        |
        | future Cloudflare Tunnel path-only ingress
        v
127.0.0.1:9193 pageview adapter
  - exact Host + Origin
  - exact route/method/content type/body bounds
  - current /srv/coloring-pages-content/public/catalog.json allowlist
  - no request logging
  - discard caller JSON after validation
        |
        | one attempt, fixed local backend body only
        v
127.0.0.1:9194 GoatCounter v2.7.0
  {"no_sessions":true,"hits":[{"path":"/coloring-page/1234567"}]}
        |
        v
private SQLite aggregate state
```

The adapter never forwards request headers, client IP, Cloudflare headers,
User-Agent, referrer, cookie, query string, campaign/UTM value, session value
or arbitrary GoatCounter field. It constructs the backend JSON from the
validated seven-digit catalog ID only. Leading zero IDs remain strings.

The future ingress is deliberately **not** source-wired here. A later exact
Cloudflare Tunnel authorization must route only
`/api/pageview` for the approved public hosts to `127.0.0.1:9193`, ordered
ahead of the existing catch-all origin, without exposing `127.0.0.1:9194`.
No wildcard GoatCounter API/admin route is allowed.

## Catalog fail-closed boundary

The adapter reads only:

```text
/srv/coloring-pages-content/public/catalog.json
```

It rejects symlinks, missing/oversized/malformed JSON, duplicate object keys,
duplicate IDs, non-seven-digit IDs, hidden/invisible records and records that
lack renderable preview/print media. Catalog failure disables analytics for
that request only; it must not affect public browsing, PNG download or print.

## Fixed source service design

Tracked units are source design only:

- `ops/systemd/ausmalwiese-goatcounter.service`
- `ops/systemd/ausmalwiese-goatcounter-pageview.service`

Both use loopback-only IP policy, `NoNewPrivileges`, strict filesystem/home
protection, no device access, bounded memory/CPU/tasks and null stdout/stderr.
The adapter receives the future count-only API token through systemd
`LoadCredential`; no credential is committed or read by source tests.

The GoatCounter unit expects a separately provisioned exact v2.7.0 binary and
pre-created private database. Source merge does not create users, directories,
credentials, databases, services or ports.

## Pinned runtime proof

The only accepted upstream runtime candidate is:

- source tag commit: `7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4`
- asset: `goatcounter-v2.7.0-linux-arm64.gz`
- bytes: `12770791`
- SHA-256:
  `ff5b2670b858bbe48802dfdc74130b6dcde2de9f5c1229b838eb9132769307dd`

The historical
`scripts/ausmalwiese_goatcounter_isolated_probe_v1.py` entrypoint is
superseded and must not be used for another runtime attempt. The canonical
future operator is
`scripts/ausmalwiese_goatcounter_isolated_probe_v2.py`; its exact
failure-preserving contract is documented in
`docs/AUSMALWIESE_GOATCOUNTER_ISOLATED_PROOF_V2.md`.

The operator performs **no download**. A future separately authorized proof
must place that exact archive as a direct child of `/tmp` on host `rpi5`
and run the v2 probe as non-root. The proof creates only a private
`/tmp/goatcounter-offline-*` fixture, verifies `version -json`, creates a
synthetic site/token, forces effective `CollectNothing=1`, starts one random
loopback listener, submits two synthetic `0427183` hits with exactly
`no_sessions:true`, shuts down cleanly and runs the structural SQLite privacy
gate. A proof failure preserves the private `0700` fixture; only a complete
PASS reaches bounded success cleanup.

The structural gate is fail-closed and permits only the pinned
aggregate-only v2.7.0 shape:

- `hits`, `bots`, browser/system aggregates, campaigns and exports remain
  zero-row requirements;
- the one graceful-shutdown `store(key="session")` housekeeping row is
  accepted only when its `sessions`, `hashes`, `paths` and `seen`
  objects are all empty;
- disabled language/location/screen-size dimensions may produce only anonymous
  aggregate buckets (`language=""`, `location=""`, `width=0`) whose
  exact site/path/day/count values duplicate the already validated pageview
  totals;
- non-empty referrer values, unsafe collection bitmasks, unexpected
  tables/columns/migrations, wrong paths/counts, WAL/SHM/journal residue,
  non-count-only synthetic API-token scope and other reviewed forbidden rows
  remain rejected.

On 2026-10-27, after the reviewed privacy-gate corrections, one separately
authorized execution on `rpi5` at exact source
`4f2bd81ddc521dbb6f86df17cdb060c088a64f95` returned:

```text
GOATCOUNTER_ISOLATED=PASS_SYNTHETIC_GOATCOUNTER_RUNTIME_ONLY_NOT_LIVE_OR_LEGAL_PROOF
```

That satisfies the pinned synthetic runtime gate only. It does **not** prove
production ingress/logging, service/path/port/credential compatibility,
backups, Cloudflare processing, German legal compliance or consent status.

## One-attempt failure semantics

The browser PR #391 already performs one page-lifetime attempt. The adapter
also sends at most one GoatCounter HTTP request. Redirects are rejected and
environment proxies are bypassed. A non-202 or ambiguous backend result is a
terminal failure for that request; there is no adapter resend, queue, retry,
rollback or cleanup. The browser remains fail-open.

## Tests

Disconnected source tests:

```text
python3 tests/test-ausmalwiese-goatcounter-pageview-v1.py
python3 tests/test-ausmalwiese-goatcounter-offline-privacy-v1.py
python3 tests/test-ausmalwiese-goatcounter-compatibility-preflight-v1.py
python3 scripts/ausmalwiese_goatcounter_pageview_adapter_v1.py --check-contract
```

They do not execute GoatCounter or access RPi5 runtime state.

## Post-merge gates

Source merge alone performs no runtime mutation. The pinned synthetic runtime
proof is complete; the next source contract is
`docs/AUSMALWIESE_GOATCOUNTER_COMPATIBILITY_PREFLIGHT_V1.md` (#1266).

Before PR #391 can be merged for production use, the remaining gates are:

1. one separately owner-authorized read-only compatibility preflight on
   `rpi5`, bound to the then-current exact merged source SHA;
2. German GDPR/TDDDG review of the exact first-party request and transient
   Cloudflare/network/proxy processing;
3. separate owner-authorized install/database/service operation;
4. separate exact path-only Cloudflare Tunnel ingress mutation and public
   verification.

The compatibility preflight authorization, when later granted, does not imply
install, credential/database access, service lifecycle, network mutation,
retry, rollback or cleanup.
