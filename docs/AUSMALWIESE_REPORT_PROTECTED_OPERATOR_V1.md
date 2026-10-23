# Ausmalwiese Report Worker — protected operator source (#1044)

**SOURCE ONLY. NOT INSTALLED. NO AUTHENTICATED NETWORK SENDER. NO PRIVATE PROVIDER. NO LIVE AUTHORITY.**

Base: RPi5_main main \`aefd6bd7614cf5a0538c14093224cac22ea78bc1\`. Owner-authorized scope is protected-operator SOURCE, offline tests, PR, CI/review only. No merge, host changes, Cloudflare access, protected data or credentials.

## Delivered source boundary

\`scripts/ausmalwiese_report_protected_operator_v1.py\` composes existing issue #1042 offline transport policies with exact six-step report-only intent, pinned original Worker SHA-256 and Git blob, a fixed-purpose nonexecuting installation layout, and a synthetic durable replay rehearsal. It rejects schema drift, other workers, extra/wildcard routes, unknown bindings and unauthorized CLI flags. The companion JSON contract is an exact closed schema. Tests are wired into \`make test\`.

The transport intent is **not a TLS sender**: it specifies \`api.cloudflare.com:443\`, verified TLS/hostname, no ambient proxy, no redirect, no automatic retry, a fixed 10-second bound and 16-KiB sanitized response bound. No socket or authentication takes place. The existing transport parser and provisioner attestation checks remain source-only and cannot establish authenticated provider evidence.

## Pinned target

- Worker: \`coloring-pages-report-v1\`; zone: \`ausmalwiese.de\`; account fingerprint SHA-256 \`3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34\`.
- Application code: \`coloring-pages\` commit \`a90c6a6a7ccca2941d99e9edddd5cfa31ac9ed18\`, \`cloudflare/report-worker.mjs\`, blob \`6d2359752d12f4a40847008fc7fdcc457124e893\`, SHA-256 \`26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1\`.
- Exactly four routes: apex and www, \`/api/report\` and \`/api/report/config\`; no wildcards or Stats modifications.
- Six bindings: \`TURNSTILE_SITE_KEY\` plain_text; \`TURNSTILE_SECRET\`, \`BREVO_API_KEY\`, \`REPORT_TO\` secret_text; \`REPORT_RATE\` 12/60 and \`REPORT_DUP\` 1/60 ratelimit, separate namespace IDs, Turnstile hostnames apex/www and action \`report\`.
- Six future operations: one sealed private version upload, one 100%-traffic deploy, and four exact route creations. A simulated O_EXCL+fsync journal prevents replay after crash; this is **not** an installed owner gate.

## Installation and evidence limits

\`installation_plan\` pins a nonexecuting release layout rooted at \`/usr/local/libexec/rpi5-ausmalwiese-report-protected\` and launcher at \`/usr/local/sbin/rpi5-ausmalwiese-report-protected\`, both intended root-owned. Supplied hashes and metadata can be forged. The layout validator checks only structure, modes, symlinks, link counts and digests and expressly does not prove runtime installation or authenticated owner approval.

**STOP before any host/Cloudflare action.** Independently review a root-owned immutable release and secure installer, a protected in-memory six-binding provider, a real authenticated TLS transport, independent Cloudflare code/version/binding/route collector, real account/zone and permission proofs, no-effect-to-Stats preflight, Brevo/Turnstile eligibility, Germany Datenschutz/retention and an owner-authenticated durable single-use gate. Then obtain separately explicit bounded LIVE authorization for that exact installed release/target. Any uncertain outcome after first mutation => STOP, no retries, rollback or cleanup.

Offline checks:

    python3 scripts/ausmalwiese_report_protected_operator_v1.py --check-contract
    python3 tests/test-ausmalwiese-report-protected-operator-v1.py

No other CLI mode exists; no deployment, API call, secret or mail test has occurred.
