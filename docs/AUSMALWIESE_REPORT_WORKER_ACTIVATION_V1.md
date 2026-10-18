# Ausmalwiese Fehler melden — current minimal activation path (#1092)

The older #1030 Brevo/Turnstile/rate-limit activation plan is historical and superseded for the current Report Worker. Its old source files may remain as historical evidence, but they are not current activation instructions.

SOURCE ONLY here. No Cloudflare or LIVE mutation is authorized.

## Current target

Fehler melden has one purpose:

POST /api/report -> coloring-pages-report-v1 -> Cloudflare Email Service EMAIL binding -> fixed project destination.

Canonical application provenance:

- coloring-pages commit 16c1ed5cccd43d28212b6a7aefbc04cae5195698
- Worker blob 4ef00f9963c68ab9a4ab5aeb4a44b8c99c76eda0
- config blob 2765e88f4c5ee7a01a5380ef52e4ff8c0688c9e6

Current config has two exact report routes and one send_email binding named EMAIL with one fixed destination_address stored only in the pinned coloring-pages config.

## Explicitly removed from the current activation path

- Brevo API and BREVO_API_KEY
- REPORT_TO secret
- Turnstile site/secret bindings
- Report rate-limit bindings and namespaces
- /api/report/config
- protected Report secrets bundle
- Stats Worker versions/deployments/routes/bindings/settings evidence
- Stats pre/post no-effect comparison

Do not revive those requirements unless a new concrete product or abuse-control need is separately reviewed.

## Future LIVE preflight

Before a future separately authorized deployment, verify only what the minimal path needs:

1. exact RPi5_main deploy/runtime source and exact coloring-pages provenance above;
2. exact target Worker and the two report routes;
3. Cloudflare Email Service is available for the account/domain;
4. sender domain/address used by the Worker is accepted by Email Service;
5. the fixed destination from the pinned coloring-pages config is accepted by Email Service;
6. the existing receiving/forwarding path reaches the intended verified mailbox;
7. no route collision with unrelated Workers.

No secret or Stats credential read is part of this preflight.

## Future verification

After one separately authorized deploy:

- prove the exact Report version is active;
- prove exactly two report routes;
- prove exactly one EMAIL send_email binding;
- send at most one separately owner-approved test report;
- verify mailbox arrival.

Any mutation error or ambiguity remains fail-closed under the normal LIVE contract.
