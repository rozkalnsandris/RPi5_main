# ausmalwiese.de — Search Console DNS TXT, source-only

This runbook specifies the **one-record** Google Search Console Domain verification for `ausmalwiese.de`. The exact DNS value was supplied by the owner after creating the Domain property in Search Console. This is not a domain/canonical SEO migration, nor a change to `coloring.rozkalns.net`.

## Frozen operation

- Entrypoint: installed root-owned `/usr/local/sbin/rpi5-cloudflare`, action `dns-ausmalwiese-gsc-txt`.
- Zone/name: **`ausmalwiese.de` apex only**, record `TXT`, TTL auto (`1`), content **exactly** `google-site-verification=CZx413pYLeISdNsik5g5cUSkztdsYyHCOUg2dASib7M`.
- Permission: existing `ausmalwiese.de`-scoped DNS credential; no Access/Tunnel credential, new token, secret or permission change.
- API: read-only `GET /zones/{zone_id}`, `GET /zones/{zone_id}/dns_records?page=1&per_page=100`; one `POST /zones/{zone_id}/dns_records` only after exact preflight; read-only list afterward. [Cloudflare create](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/create/), [list](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/list/).
- The preflight accepts existing apex CNAME and unrelated TXT records, but stops if an apex Google verification TXT already exists (same or different value), zone isn't active/Free, DNS inventory is incomplete or the SHA baseline drifts.
- On an ambiguous or failed write/post-write read, **STOP** without retry, cleanup, rollback or alternate mutation. Post-write verifies the single returned record ID and unchanged existing DNS inventory.

## Separate owner-gated LIVE path

Source PR, tests and merge do **not** authorize DNS changes, operator replacement or Google verification. After review and explicit merge, a separate LIVE authorization must bind the installed source upgrade, exact release identity and permissions; only after that upgrade is separately authorized/verified may the operator be used with a fresh, separately authorized TXT mutation.

Read-only preparation, **once the reviewed operator is installed at the merged exact SHA**:

```bash
sudo /usr/local/sbin/rpi5-cloudflare dns-ausmalwiese-gsc-txt --expected-main <exact-installed-main-sha>
```

The sanitized response provides `baseline_sha256`. Only after exact owner LIVE approval for this DNS action:

```bash
sudo /usr/local/sbin/rpi5-cloudflare dns-ausmalwiese-gsc-txt --expected-main <exact-installed-main-sha> --apply --expected-baseline <exact-current-baseline-sha256> --confirm CREATE-AUSMALWIESE-GSC-TXT
```

This is operator **documentation**, not authorization to run either command on a host from this SOURCE-only PR. After the record is verified, finish ownership verification in Google Search Console separately; `GSC Wizard` registration, sitemap submission and canonical-domain migration are separate scopes.
