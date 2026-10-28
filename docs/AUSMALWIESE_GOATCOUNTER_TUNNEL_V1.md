# GoatCounter pageview tunnel operation

Outcome issue: #1270. Source preparation only; merge does not execute this operator.

## Current evidence and remaining outcome

The private installation at RPi5_main `45eb529a8963ea65fc09a8511f78bc847c9ae9bc`
succeeded on 2026-10-28. The canonical sanitized receipt is
[PR #1269 comment](https://github.com/rozkalnsandris/RPi5_main/pull/1269#issuecomment-6464118635).
Both services were active/enabled with zero restarts, on loopback ports 9193/9194;
the installed source hashes, count-only token scope and CollectNothing=1 were
verified. No pageview events were sent. This is historical installation evidence,
not fresh health evidence or permission to expose collection. That installation
authorization is consumed.

The remaining network connection is exactly:

`https://{ausmalwiese.de,www.ausmalwiese.de}/api/pageview -> 127.0.0.1:9193`

The adapter alone calls the private GoatCounter backend on 9194. No public admin,
backend API, DNS change, Worker deployment or application change is included.
The client in coloring-pages #391 remains held at
`d8f0f6ea5116ec8188684d76bf4d2d75ff62ef6f` until all public gates pass and
the owner separately authorizes its exact merge/deployment scope.

## Operator behavior

`scripts/ausmalwiese_goatcounter_tunnel_v1.py` reuses only the credential loader,
HTTP client and validation constants from `scripts/cloudflare_rdc_operator.py`.
Both files must be obtained from the same reviewed immutable revision, their
Git blob identities verified before authorized execution. Do not execute an
unreviewed checkout as root. No installed operator or wrapper is assumed.

Default execution is read-only. It reads only the existing root-owned 0600
`/etc/rpi5-secrets/cloudflare/tunnel-writer.json` using the established loader;
credential access itself needs explicit owner authorization. It does not read
`/etc/cloudflared`, application configuration, logs, SQLite or GoatCounter secrets.
The token is used only in memory to call the fixed Cloudflare HTTPS API. Proxy
environment variables and redirects are disabled. No secret is placed in argv,
environment, evidence or exception output. There are no retries.

The account is SHA-256-pinned to the existing reviewed Ausmalwiese Stats account
binding before any API call; a different credential account is rejected.

Allowed endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/accounts/{account}/tokens/verify` | Active account token |
| GET | `/accounts/{account}/cfd_tunnel?name=rpi5-tunnel&is_deleted=false&per_page=100` | Exact remote-managed tunnel |
| GET | `/accounts/{account}/cfd_tunnel/{id}/configurations` | Baseline, immediate prewrite and postwrite |
| PUT | `/accounts/{account}/cfd_tunnel/{id}/configurations` | At most one `{"config": desired}` body |

Read-only budget: 3 GET, zero writes. Apply budget: 5 GET and at most one PUT.
All IDs/configuration remain in memory; output contains finite state/booleans and
a SHA-256 baseline binding tunnel identity, version and complete configuration.

The transformer inserts `^/api/pageview$` immediately before each existing exact
hostname fallback. It explicitly sets the origin Host to that hostname, preserving
the adapter's same-origin check. It preserves every previous rule, order and
top-level setting. It refuses global originRequest inheritance, matching wildcard
hosts, early catch-alls, ambiguous/duplicate app fallbacks, any other path rule
for these hosts, partial installation, and a final rule other than exact
`http_status:404`. An already-exact installation is a read-only no-op.
Conservative rejection means review the actual shape; never relax the checks
or overwrite a conflict during the LIVE operation.

Apply requires the expected baseline and explicit public-exposure confirmation.
The complete configuration/version is read again immediately before PUT, and
the postcheck requires exact desired configuration and a newer version.
Cloudflare's API does not document a conditional config PUT: the second GET
cannot eliminate the race between GET and PUT. **An exclusive operational
single-writer window is a prerequisite.** No shared tunnel writer may run then.

After dispatch, any write exception, malformed response, postcheck error or
mismatch returns STOP_ERROR with write_attempted=true and unknown mutation
status. Preserve sanitized evidence; do not retry, rollback, clean up or deploy
the frontend. A fresh read-only reconciliation needs its own applicable authority.

## Execution gates

Before even read-only execution, bind the exact merged source SHA, host rpi5,
two verified source files, existing tunnel credential access and the three GETs.
Example operator arguments, **not authorization**:

```sh
python3 scripts/ausmalwiese_goatcounter_tunnel_v1.py \
  --confirm-read READ_GOATCOUNTER_TUNNEL_BASELINE
```

Before apply, prepare one exact owner decision including all of:

1. Fresh private service/binary/loopback evidence; no assumed health from source.
2. Fresh edge route/settings evidence, including no Worker interception of this
   path, redirects or unexpected request logging. The source Stats contract lists
   `/api/stats/*` and `/q`, which do not overlap; it is not runtime evidence.
   Broader `/api/*` or host-wide Worker routes could prevent reaching the tunnel.
3. The independent public privacy/legal assessment required by the existing
   GoatCounter design: CDN/origin processing and log retention, aggregate
   retention, no individual-hit/session storage, notice and applicable legal
   basis. Synthetic and private-install PASS do not satisfy these gates.
4. Exact source SHA, baseline digest, single-writer window, one PUT for these two
   routes, protected credential/config inspection, stop-on-failure semantics.
5. A separately authorized verification plan: non-counting GET/invalid request
   behavior first; any real pageview test is a separately named data mutation.

Only then add `--apply --expected-baseline <verified-sha256>` and
`--confirm-public-exposure EXPOSE_GOATCOUNTER_PAGEVIEW_AFTER_PUBLIC_GATES`.
These flags acknowledge a decision made outside the program; they cannot prove
legal readiness or create owner authorization. Output always reports
public_readiness_verified=false to avoid conflating route correctness with it.

Opening this route exposes a write endpoint even before the browser client is
merged. Therefore public gates must precede ingress apply, not only frontend
deployment. This source PR changes no runtime, CI dispatch or installed service.

## Tests and documentation

`python3 tests/test-ausmalwiese-goatcounter-tunnel-v1.py` runs disconnected
regressions through `make validate`; it never calls Cloudflare or reads secrets.

Official sources reviewed 2026-10-28:

- [Cloudflare ingress matching](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/): ordered matching, Go regex paths and final catch-all.
- [Cloudflare origin parameters](https://developers.cloudflare.com/tunnel/configuration/): httpHostHeader override.
- [Cloudflare remote configuration API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/): full config update and versioned observation.
- [Workers routes](https://developers.cloudflare.com/workers/configuration/routing/routes/): URL route selection preceding the origin.
