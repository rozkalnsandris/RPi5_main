# Ausmalwiese legacy 301 installed runtime boundary (#1116)

**Status: SOURCE ONLY · not installed · no credential access · no Cloudflare request · no LIVE authority.**

This outcome packages the already-reviewed #996/#1114 redirect inventory/get/write
logic behind one fixed root-owned runtime and one fixed owner-TTY credential
provisioner. A merge only makes the source reviewable/canonical; it does not
install anything or authorize the redirect.

## Fixed installed layout

Future separately authorized installation may create only:

- `/usr/local/sbin/rpi5-ausmalwiese-redirect-write` — root:root 0500;
- `/usr/local/sbin/rpi5-ausmalwiese-redirect-write-provision` — root:root 0500;
- `/usr/local/libexec/rpi5-ausmalwiese-redirect-write/` — root:root 0700;
- `inventory.py`, `adapter.py`, `write.py`, `release.json` — root:root 0400.

The installer requires an exact clean `RPi5_main/main`, verifies every tracked
source byte against Git, refuses overwrite/symlink ambiguity, and writes a release
manifest binding the exact source SHA plus SHA-256 for the launcher, provisioner
and all three imported modules. The runtime rejects checkout execution and verifies
all installed bytes, owners, modes and one-link regular-file metadata before any
credential read.

The installer itself has no credential access and makes no Cloudflare request.

## Protected credential

The only credential path is:

`/etc/rpi5-secrets/cloudflare/ausmalwiese-redirect-write.json`

Expected metadata is root:root 0600 under the already-existing root-owned 0700
Cloudflare secrets directory. Exact JSON fields:

- `zone_name` = `rozkalns.net`;
- `zone_id` = 32 lowercase hex;
- `api_token` = the separately authorized zone-scoped Dynamic URL Redirects Write token.

The fixed provisioner accepts the zone ID and token only from the controlling
`/dev/tty` with echo disabled. It never accepts credential material from argv,
environment variables, stdin, GitHub, chat or logs. It performs an exclusive
single create and never overwrites an existing credential. It does not create a
Cloudflare token or alter token permissions.

Credential content is never emitted. Any ambiguous state after the credential
file create dispatch is terminal; no retry, unlink, cleanup or replacement occurs.

## Runtime modes

The installed runtime exposes only two modes, both requiring an exact installed
release identity and one protected credential read.

### Sanitized preflight

Requires exact confirmation
`OWNER-AUTHORIZED-REDIRECT-WRITE-PREFLIGHT`.

It reuses the fixed GET adapter and returns only the #1114 sanitized preflight
shape: fixed labels, `baseline_sha256`, operation class, and whether a mutation
would be required. It performs no provider write and never returns zone/ruleset/
rule IDs, raw rules, credential material or provider error bodies.

### Expected-baseline apply

Requires exact confirmation
`OWNER-AUTHORIZED-REDIRECT-WRITE-APPLY` plus the exact 64-hex baseline from the
fresh preflight.

The runtime calls the already-reviewed
`scripts/ausmalwiese_redirect_write_v1.py` core. That core independently
re-reads the provider state, fails on baseline drift, and permits at most one
exact provider write: create the phase ruleset, add the exact rule, or update the
one exact legacy-host rule. The write budget is consumed immediately before
dispatch. Post-write sanitized inventory must prove the desired rule and unchanged
unrelated rule semantics.

No retry, rollback, cleanup, fallback transport or second write is available.

## Future #996 COMPOSITE LIVE

After this source is merged, the owner-visible flow remains:

`MERGE -> one COMPOSITE LIVE`

The future Composite LIVE must explicitly freeze the exact current main/runtime
bytes, host, credential access/provisioning class, Cloudflare redirect write class,
fresh baseline and the parent #996 ordered stages. Installation/provisioning are
not standing authority; if needed they are bounded technical steps inside that
single separately authorized LIVE envelope.

The redirect apply remains the final stage only after:

1. Stats Gate A acceptance;
2. Stats Worker and `/q` acceptance;
3. sitemap publication and new-domain acceptance;
4. public health/report/Stats checks.

Any earlier stage failure prevents the legacy redirect write.

## Source verification

Offline regression:
`python3 tests/test-ausmalwiese-redirect-write-runtime-v1.py`

Machine contract:
`ops/contracts/ausmalwiese-redirect-write-runtime-v1.json`

This source grants no host install, credential read/provisioning, Cloudflare
request/write, token creation, permission/settings change, DNS/WAF/Access/Tunnel,
Stats/D1, sitemap, LIVE, retry, rollback or cleanup authority.
