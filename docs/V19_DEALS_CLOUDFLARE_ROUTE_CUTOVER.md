# V19 Deals Cloudflare route cutover contract

## Status

**Source review pending. Production route remains on the LAN origin until the explicit owner command succeeds.**

This phase moves only the remotely-managed Cloudflare Tunnel ingress entry for
`deals.rozkalns.net` from the temporary LAN origin to the already verified
loopback listener.

The application-side prerequisite is complete: Hermes Deals issue #307 has a
reviewed temporary dual bind serving both `192.168.0.180:9128` and
`127.0.0.1:9128`, and its host-side `check`, `apply-dual`, and `verify-dual`
gates passed before this route phase began.

## Ownership

`RPi5_main` owns the shared RPi5 ingress architecture and reviews this route
change. The Hermes Deals repository owns its application listener and may verify
its own local/public path, but it does not own the shared `cloudflared.service`
or Tunnel credential.

The Tunnel remains remotely managed. No local `config.yml` is introduced.

## Exact current and target state

Hostname:

```text
deals.rozkalns.net
```

Required pre-cutover service:

```text
http://192.168.0.180:9128
```

Target service:

```text
http://127.0.0.1:9128
```

The complete reviewed hostname set is exactly:

- `rozkalns.net`
- `tech.rozkalns.net`
- `deals.rozkalns.net`
- `hermes.rozkalns.net`
- `portainer.rozkalns.net`
- `grafana.rozkalns.net`
- `ha.rozkalns.net`
- `adguard.rozkalns.net`
- `kuma.rozkalns.net`
- `prometheus.rozkalns.net`

The final ingress item must remain the catch-all `http_status:404` rule.
Unknown, missing, duplicated, reordered-to-invalid catch-all, or otherwise
unexpected route state fails closed before any write.

## Cloudflare API contract

Cloudflare documents remotely-managed Tunnel configuration through:

```text
GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
PUT /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
```

The PUT replaces the Tunnel configuration, so the operator always reads the full
configuration, proves the expected route set and current Deals service, changes
only the one `service` value in memory, and sends the complete guarded
configuration back. It then re-reads the remote configuration and requires exact
semantic equality with the intended result.

The operator also reads the Tunnel object and requires:

```text
name = rpi5-tunnel
config_src = cloudflare
```

## Credential boundary

The GitHub-hosted route job reads exactly these encrypted Actions secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_TUNNEL_ID`

The API token should be narrowly scoped to the target account and to a Cloudflare
Tunnel/Connector write permission accepted by the Cloudflare configuration API.
It is not the `cloudflared` connector token.

The workflow never prints these values, never uploads an artifact, never sends
them to the self-hosted RPi5 runner, and never includes them in issue evidence.
If any required secret is absent or malformed, the operation is blocked before a
Cloudflare write.

## Owner-only GitHub commands

Only exact comments by repository owner `rozkalnsandris` on RPi5_main issue #61
are authorized:

```text
/rpi5-61 check
/rpi5-61 cutover
/rpi5-61 verify
```

`check` is read-only and requires the current LAN route. `cutover` repeats the
same preflight immediately before the PUT and changes only the Deals service.
`verify` is read-only and requires the loopback route after cutover.

There is no arbitrary hostname/origin argument and no generic Cloudflare shell
escape. A manually callable rollback command is intentionally not exposed in
this bridge.

## Drift and transaction safety

Before cutover the operator:

1. validates credential shape without printing it;
2. verifies exact Tunnel name and remote-management mode;
3. reads the complete configuration;
4. requires exactly ten reviewed hostnames plus the final catch-all;
5. requires the Deals service to be exactly the old LAN origin;
6. verifies the unauthenticated external Deals request is still redirected to a
   `*.cloudflareaccess.com` host;
7. re-reads the configuration immediately before the write and requires both the
   complete config and reported version to be unchanged;
8. constructs the desired config and proves replacing the one Deals service back
   with the old value reproduces the exact pre-write config.

After PUT it:

1. re-reads the full configuration;
2. requires exact equality with the intended config;
3. revalidates the full route/catch-all contract with the loopback Deals origin;
4. revalidates the Cloudflare Access redirect.

If a post-write configuration or edge gate fails, the operator attempts one
bounded automatic rollback by PUTting the exact in-memory pre-write config and
then requiring exact remote equality, old Deals LAN origin, and the Access edge
redirect. A failed rollback is reported as requiring immediate review; raw API
responses are not published.

## External verification limitation

The unauthenticated GitHub-hosted request proves the PRIVATE hostname remains
behind Cloudflare Access, but an Access redirect alone does not prove that an
authorized request reached the new origin. Therefore the route step is followed
by the already installed Hermes Deals host-side `verify-dual` gate to re-prove
the local loopback listener and shared connector health. Authenticated/private
end-to-end verification remains required before the application removes its LAN
listener.

## Explicit exclusions

This phase does not:

- read or rotate the Tunnel connector token;
- start, stop, restart, reload, or replace `cloudflared.service`;
- edit Cloudflare Access applications or policies;
- edit DNS records;
- edit UFW;
- run Docker or alter Hermes Deals containers;
- modify the Hermes Deals database, collectors, Review state, or API deployment;
- change any hostname other than the one exact Deals `service` field.

## Completion sequence

1. merge reviewed V19 source and tests;
2. run `/rpi5-61 check` and require PASS;
3. run `/rpi5-61 cutover` and require PASS;
4. run `/rpi5-61 verify` and require loopback PASS;
5. run the Hermes Deals host-side `verify-dual` gate again;
6. perform authenticated/private external verification;
7. return to Hermes Deals #307 for a separately reviewed dual-bind → loopback-only
   application transition and only then consider removing the obsolete LAN 9128
   UFW allowance.
