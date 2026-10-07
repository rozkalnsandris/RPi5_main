# PUBLIC zone verification contract v1

Status: **source readiness only**  
Roadmap: `RPi5_main#60` Phase 3  
Implementation: `RPi5_main#816`  
Machine contract: `ops/contracts/public-zone-verification-v1.json`

## Purpose

Phase 3 verifies that the services classified as `PUBLIC` by the canonical ingress registry still behave as intentionally public services without widening their origin exposure.

The v1 Phase 3 verification snapshot is intentionally fixed to the two services it actually verified:

- `apex-web` / `rozkalns.net`;
- `hermes-tech` / `tech.rozkalns.net`.

The canonical registry may gain later reviewed PUBLIC services without rewriting that historical receipt. Coloring Pages and, under #911, `weather-public` / `weather.rozkalns.net` are later registrations. They inherit the same PUBLIC source-policy invariants but do **not** retroactively claim Phase 3 runtime PASS. Their runtime verification/remediation remains separately gated.

## Source policy expectations

Each PUBLIC service must satisfy the same public-safe policy:

- Cloudflare Access is not required;
- Access class is `NONE`;
- desired origin class is `loopback`;
- LAN break-glass is forbidden;
- no LAN-origin firewall exception is required;
- the shared connector remains owned by `RPi5_main`.

These are source-policy expectations only. They are not claims about the currently running host, Cloudflare account, firewall or connector.

## Anonymous HTTP expectation

A later authorized read-only runtime verification uses anonymous HTTPS `GET /` for both PUBLIC hostnames.

PASS behavior is:

- response status class is `2xx` or `3xx`;
- a redirect, if any, remains a public-endpoint redirect;
- no Cloudflare Access challenge is encountered;
- no response body is retained in the evidence artifact.

The contract deliberately validates behavior classes instead of page content so Phase 3 does not couple ingress verification to application copy or presentation.

## Origin and firewall expectation

For the two historical Phase 3 services, and as source policy for later PUBLIC registrations:

- route/origin class must verify as `loopback`;
- no obsolete LAN-origin firewall exception may be present.

For Weather specifically, #911 records the current route-origin class as `unknown` until a fresh bounded audit proves it; this avoids turning source registration into a false runtime PASS.

The evidence records only these classes/booleans. It must not record private addresses, internal origin ports, firewall source ranges or protected host configuration.

## Shared connector expectation

The shared connector verification is bounded to:

- `cloudflared.service` active;
- `cloudflared.service` enabled;
- installed unit identity matches the reviewed source unit;
- four active edge connections.

The four-connection target comes from the reviewed V13 ownership contract. Runtime verification may summarize the count, but it must not persist the metrics payload.

## Sanitized evidence schema

The machine contract allowlists every evidence field.

Per PUBLIC service it allows only:

- service ID and public hostname;
- anonymous HTTP status class;
- redirect class;
- Access-challenge presence boolean;
- origin class;
- LAN-firewall-exception presence boolean;
- PASS/FAIL.

For the shared connector it allows only active/enabled booleans, reviewed-unit identity match, active edge-connection count and PASS/FAIL.

The evidence must not contain HTTP bodies, cookies, authorization headers, account/tunnel/Access identifiers, credential or token values, private origin coordinates, process environments, application config or application logs.

## Source vs runtime boundary

Merging this source outcome:

- does not prove current anonymous external access;
- does not prove current Cloudflare Access configuration;
- does not prove the current Tunnel route or bind class;
- does not prove current firewall state;
- does not prove current connector health;
- does not authorize any read of protected runtime data;
- does not authorize any production mutation.

Phase 3 stays incomplete after source merge.

A fresh owner authorization is required for the bounded read-only runtime verification. If that verification finds drift, remediation is a separate issue and separate owner-gated mutation; verification authority must not be converted into repair authority.

## Runtime PASS gate

Phase 3 may be marked COMPLETE only after a later sanitized evidence receipt proves, for both PUBLIC services:

1. anonymous HTTP PASS;
2. no Access challenge;
3. loopback origin class;
4. no obsolete LAN firewall exception;
5. shared connector health PASS.

Only then may #60 continuity advance to Phase 4.