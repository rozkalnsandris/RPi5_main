# Ausmalwiese household GoatCounter `/count` WAF — source contract v1 (#1420)

Status: **SOURCE ONLY / NOT DEPLOYED**

This outcome defines a bounded Cloudflare zone custom-rule operator for excluding owner/household traffic from GoatCounter by blocking only matching `/count` requests at Cloudflare edge. It does not install the operator, provision a credential, read household addresses, call Cloudflare, or create a rule.

## Exact scope

- zone: `ausmalwiese.de`;
- hosts: `ausmalwiese.de` and `www.ausmalwiese.de`;
- path: exact `/count`;
- phase: `http_request_firewall_custom`;
- action: `block`;
- source predicate: `ip.src in {...}` with validated public exact IPs and/or bounded CIDR prefixes;
- stable rule ref: `ausmalwiese-household-goatcounter-exclusion-v1`.

No wildcard host/path, DNS, Tunnel, Worker, Access, GoatCounter, service or database change belongs to this outcome.

Cloudflare documents zone custom rules for all plans, including Free, in the `http_request_firewall_custom` phase. Inline `in` lists support individual IP addresses and CIDR ranges, including IPv6. A Block action stops matching requests at Cloudflare rather than forwarding them to the origin.

Official references:
- https://developers.cloudflare.com/waf/custom-rules/
- https://developers.cloudflare.com/waf/custom-rules/create-api/
- https://developers.cloudflare.com/ruleset-engine/rules-language/values/
- https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/ip.src/

## Why native GoatCounter Ignore IPs is not sufficient

Issue #1415 established that pinned GoatCounter v2.7.0 matches native `IgnoreIPs` as exact addresses. Sanitized RPi5 preflights later observed public IPv4 and IPv6, plus multiple global IPv6 prefixes/mixed prefix lengths. That does not prove one stable household IPv6 address or prefix that GoatCounter can represent natively.

The WAF design can use an exact IPv4 and, when separately proven, bounded IPv6 CIDR coverage. It must never claim whole-house coverage unless the protected future preflight establishes the intended source set.

## Address validation

`scripts/ausmalwiese_goatcounter_household_waf_v1.py` accepts raw address material only from a future installed operator's hidden local controlling TTY. It does not accept household addresses through chat, CLI arguments, environment variables, stdin, GitHub or logs.

Validation is fail-closed:
- 1–8 entries;
- canonical public IPv4/IPv6 exact addresses;
- canonical IPv4 CIDR no broader than `/24`;
- canonical IPv6 CIDR no broader than `/48`;
- private, loopback, link-local, multicast, unspecified, reserved, scoped and malformed addresses rejected;
- duplicates and empty input rejected.

The `/24` and `/48` lower bounds are conservative source guards, not claims about the owner's ISP delegation. A future protected preflight must prove the selected source actually represents the intended household.

## Privacy boundary

Raw household IP/CIDR values remain ephemeral in the operator process until a separately authorized apply. Public-safe preflight output contains only operation shape, existing-rule count, source-type counts, and `writes=0`.

If LIVE activation is approved, the Cloudflare custom-rule expression necessarily stores the exact IP/CIDR material in Cloudflare configuration. That privacy trade-off must be part of the later owner decision.

## Rulesets API contract

The operator follows the reviewed Rulesets API pattern from `scripts/cloudflare_zone_bot_waf.py`:

1. Verify exact installed release and dedicated zone credential.
2. `GET /zones/{zone_id}` and require exact `ausmalwiese.de`.
3. `GET /zones/{zone_id}/rulesets/phases/http_request_firewall_custom/entrypoint`.
4. Accept only a valid zone entrypoint or `404`.
5. Reject target-ref/expression conflicts and conservatively stop when five existing rules consume the Free-plan quota.
6. Existing entrypoint: allow only one `POST /zones/{zone_id}/rulesets/{ruleset_id}/rules`.
7. Absent entrypoint: allow only one `POST /zones/{zone_id}/rulesets` with the single target rule.
8. Post-write `GET` verifies all prior rules unchanged/in order and exactly one correct appended target.
9. After the first POST, any error or ambiguity is STOP. No retry, rollback, cleanup, PUT, PATCH, DELETE or unrelated-rule replacement.

## Protected runtime prerequisites

Protected `--preflight`/`--apply` modes require:
- `/usr/local/sbin/rpi5-ausmalwiese-household-waf`;
- `/usr/local/libexec/rpi5-ausmalwiese-household-waf/release.json`;
- dedicated root-only `/etc/rpi5-secrets/cloudflare/ausmalwiese-zone-waf-writer.json`;
- credential schema only `zone_id`, `zone_name`, `api_token`;
- exact zone `ausmalwiese.de`;
- Zone Read + Zone WAF Edit rights.

This outcome deliberately does not include installer or credential provisioning. Those cross separate root/secret trust boundaries and require their own reviewed source and explicit owner authorization. Tunnel/Access credentials must not be reused.

## Verification

Offline preview, no network/secret access:

```bash
python3 scripts/ausmalwiese_goatcounter_household_waf_v1.py --plan
```

Disconnected tests:

```bash
python3 tests/test-ausmalwiese-goatcounter-household-waf-v1.py
```

The tests cover exact host/path scope, IP/CIDR validation, overbroad-prefix rejection, duplicate/conflicting rules, rule preservation, quota gate, zero-write preflight, one-write apply ceiling, sanitized output and no CLI/environment raw-address input.

## Gates after source merge

Source merge does not authorize Cloudflare or RPi5 mutation. Remaining gates are:
1. reviewed installer/provisioner source and explicit install/credential authorization;
2. protected household source discovery with sanitized evidence;
3. read-only Cloudflare inventory/quota preflight;
4. one explicit Cloudflare WAF create authorization bound to the reviewed installed release and exact zone/rule operation.

No rule is LIVE until those gates are separately satisfied.


## First-install and dedicated credential source (#1422)

The operator source is now paired with a reviewed **first-install-only** source installer:
`scripts/install-ausmalwiese-goatcounter-household-waf-v1.py`.

The installer does not run automatically. Its default mode is a read-only preflight requiring an unprivileged caller, clean exact `main`, canonical GitHub origin, tracked fixed source, safe root-controlled parent metadata, and absent fixed targets (including dangling symlinks). It captures the operator bytes and exact release metadata before any future mutation.

A future separately authorized install may perform only three fixed `sudo -n` GNU coreutils mutations:

1. create `/usr/local/libexec/rpi5-ausmalwiese-household-waf` as root:root 0700;
2. install captured operator bytes to `/usr/local/sbin/rpi5-ausmalwiese-household-waf` as root:root 0500;
3. install captured `release.json` as root:root 0400.

No privileged Python, shell `-c`, caller-selected path/command, overwrite, update, replace, sudoers edit, retry, rollback or cleanup is part of the installer. After the first root write is dispatched, any error/ambiguity is terminal and the installation may be partial.

Read-only source preflight form after a future exact checkout sync:

```bash
python3 scripts/install-ausmalwiese-goatcounter-household-waf-v1.py --expected-main <exact-current-main>
```

The future install form exists in source but requires its own exact LIVE authorization:

```bash
python3 scripts/install-ausmalwiese-goatcounter-household-waf-v1.py --expected-main <exact-current-main> --apply --confirm INSTALL-AUSMALWIESE-HOUSEHOLD-WAF
```

Merging this source does **not** authorize either command to mutate the host.

### Dedicated Cloudflare credential provisioning

The installed root-owned operator now includes a separately gated `--provision-secret` mode. It requires exact installed-release verification and an already existing private root-owned `/etc/rpi5-secrets/cloudflare` directory. The fixed secret target is:

`/etc/rpi5-secrets/cloudflare/ausmalwiese-zone-waf-writer.json`

The only allowed credential schema is `zone_id`, `zone_name=ausmalwiese.de`, `api_token`. Zone ID and token are accepted only through hidden `getpass` prompts on the local controlling TTY. They are not accepted through chat, GitHub, CLI arguments, environment variables or stdin.

Before any secret-file mutation, provisioning performs GET-only provider checks:
- exact `ausmalwiese.de` zone identity;
- the `http_request_firewall_custom` entrypoint, accepting either a valid zone entrypoint or `404`.

Provisioning performs no WAF `POST`, no household IP/CIDR discovery and no rule creation. A successful GET proves only the required read path, **not** Zone WAF Write permission. The owner must separately create/verify a dedicated token scoped only to the `ausmalwiese.de` zone with Zone Read + Zone WAF Write; Tunnel, Access, Worker, D1 or other credentials must not be reused.

The secret file's exclusive `O_EXCL|O_NOFOLLOW` root-only 0600 create is the first and only provisioning mutation. Any error after creation begins is STOP with no automatic retry/rollback/cleanup.

Future provisioning form, only after separately authorized install and credential-provision gates:

```bash
sudo -n /usr/local/sbin/rpi5-ausmalwiese-household-waf --provision-secret --expected-main <exact-installed-release-sha> --confirm PROVISION-AUSMALWIESE-ZONE-WAF-SECRET
```

This command must be entered only in an owner-controlled local/SSH terminal with a controlling TTY; credential values themselves must never be pasted into chat.

### Remaining gates after #1422 source merge

1. exact RPi5 checkout sync/read-only installer preflight;
2. separate first-install LIVE authorization for the fixed three-file installation;
3. separate owner-local-TTY dedicated credential provisioning authorization;
4. protected household IP/CIDR discovery/preflight with sanitized output only;
5. GET-only Cloudflare rule inventory/quota preflight;
6. separate exact one-write WAF creation authorization.

Source merge alone completes none of these LIVE gates.
