# GoatCounter SIMPLE: household traffic exclusion (#1415)

**SOURCE ONLY.** This contract adds no LIVE read, public `/count` probe,
GoatCounter setting write, database edit, Cloudflare change, service lifecycle
operation or credential access. It reuses the client-IP trust predicates from
#1352 and returns only fixed PASS/STOP codes.

## Pinned upstream behavior

Pinned runtime source remains
`arp242/goatcounter@7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4`
(v2.7.0).

- `handlers/backend.go` installs `zhttp/mware.RealIP()` before `/count`.
- The pinned `zhttp` RealIP middleware prefers `CF-Connecting-IP`, then other
  proxy headers, and rewrites `r.RemoteAddr`. Its own source warns that header
  trust depends on the concrete proxy boundary.
- `handlers/count.go` compares every `SiteSettings.IgnoreIPs` entry to
  `r.RemoteAddr` with exact string equality before appending a hit.
- `SiteSettings.Validate` validates each IgnoreIPs item as an individual IP.
  Native Ignore IPs is therefore an exact-address list, not a CIDR or prefix
  exclusion mechanism.

A shared stable public IPv4 can represent an IPv4-NAT household as one exact
address. Stable public IPv6 addresses may be listed individually. A rotating
IPv6 privacy address set, dynamic/unknown public IPv4, or a desired whole
IPv6 prefix cannot honestly be represented as complete household coverage by
the native v2.7.0 Ignore IPs list.

Upstream references:
- https://www.goatcounter.com/help/skip-dev
- https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/handlers/count.go
- https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/handlers/backend.go
- https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/settings.go
- https://github.com/arp242/zhttp/blob/9a43cabb6d05/mware/realip.go

## Sanitized source planner

`evaluate_household_exclusion(evidence)` accepts only classifications, never
raw owner/visitor IP values:

- `ip`: the exact reusable #1352 trust predicates: loopback-only tunnel peer,
  pinned vhost, trusted proxy overwrite, verified real-client RemoteAddr,
  spoof-negative result and HTTPS forwarding;
- `egress.ipv4`: `shared_stable_exact`, `absent`, or `dynamic_or_unknown`;
- `egress.ipv6`: `stable_exact_set`, `absent`, or `rotating_or_unknown`;
- `mutation`: exact target `goatcounter_site_settings`, exact field
  `ignore_ips`, `preserve_other_settings=true`, `direct_db_edit=false`.

Only stable exact-address cases return
`PASS_HOUSEHOLD_EXCLUSION_SOURCE_ONLY`. Dynamic IPv4, rotating IPv6, missing
egress evidence, malformed trust evidence or a wider mutation contract STOP.

`exact_ignore_ips_valid()` and `exact_ignore_ips_cover()` are pure in-memory
helpers for a future separately authorized operator. They return booleans
only. They reject CIDR/prefixes, non-canonical text, scoped/link-local/private
addresses and duplicates, and never return the supplied address strings.

## Future protected preflight — separately owner-authorized

Before any setting mutation, a trusted bounded operator must prove the
following without printing or persisting owner IPs in GitHub evidence:

1. `/count` reaches GoatCounter through the expected cloudflared/loopback
   boundary and pinned vhost.
2. The post-middleware `RemoteAddr` is the real client address.
3. A spoof-negative request cannot override that address through
   `CF-Connecting-IP`, `X-Forwarded-For`, `X-Real-IP` or equivalent input.
4. Household egress is actually representable by a stable exact IPv4 and/or a
   bounded stable exact IPv6 set.
5. The proposed exact addresses cover the observed household egress using
   exact string matching.

The operator's public-safe result may contain only fixed status codes and
non-sensitive classifications. Raw owner/visitor IPs, headers, database rows,
credentials or provider responses must not be emitted.

## Future setting mutation — separately owner-authorized

The smallest allowed change is one normal GoatCounter site-settings update
whose only semantic difference is `SiteSettings.ignore_ips`. It must preserve
every other site setting, including `Collect`. No direct ad-hoc database edit,
Cloudflare route change, new public admin endpoint or service restart is part
of this contract.

If stable whole-house coverage cannot be proven, STOP instead of applying a
partial filter. The documented fallback is per-browser GoatCounter
`#toggle-goatcounter`; a network/edge exclusion would be a different trust
boundary and needs its own review and authorization.

Verification:
`python3 tests/test-ausmalwiese-goatcounter-simple-readiness-v1.py`.
