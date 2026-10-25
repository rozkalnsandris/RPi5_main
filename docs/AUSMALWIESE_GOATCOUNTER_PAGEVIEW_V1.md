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

`scripts/ausmalwiese_goatcounter_isolated_probe_v1.py` performs **no
download**. A future separately authorized proof must place that exact archive
as a direct child of `/tmp` on host `rpi5` and run the probe as non-root.
The probe creates only a private `/tmp/goatcounter-offline-*` fixture,
verifies `version -json`, creates a synthetic site/token, forces effective
`CollectNothing=1`, starts one random loopback listener, submits two
synthetic `0427183` hits with exactly `no_sessions:true`, shuts down cleanly
and runs the structural SQLite privacy gate.

The structural gate rejects:

- any row in `hits`, `bots` or `store`;
- browser/system/location/language/campaign/size personal-dimension stats;
- non-empty referrer values;
- unsafe `Collect=0` defaults or Session bits;
- unexpected tables/columns/migrations;
- wrong page paths/counts;
- WAL/SHM/journal residue;
- non-count-only synthetic API-token scope;
- exports and other reviewed forbidden rows.

Passing is evidence only for that synthetic pinned runtime. It does **not**
prove source reproducibility, production ingress/logging, backups, Cloudflare
processing, German legal compliance or consent status.

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
python3 scripts/ausmalwiese_goatcounter_pageview_adapter_v1.py --check-contract
```

They do not execute GoatCounter or access RPi5 runtime state.

## Post-merge gates

Source merge alone performs no runtime mutation. Before PR #391 can be merged
for production use, all of the following remain separate gates:

1. exact merged RPi5 source + exact pinned archive synthetic proof on `rpi5`;
2. proof that the required service users/paths/ports/credential boundary can
   be provisioned without conflicting with current runtime;
3. German GDPR/TDDDG review of the exact first-party request and transient
   Cloudflare/network/proxy processing;
4. separate owner-authorized install/database/service operation;
5. separate exact path-only Cloudflare Tunnel ingress mutation and public
   verification.

No LIVE retry/rollback/cleanup is implied.
