# Ausmalwiese Fehler melden — current minimal activation path (#1098)

The older #1030 Brevo/Turnstile/rate-limit activation plan is historical and superseded for the current Report Worker. Its old source files may remain as historical evidence, but they are not current activation instructions.

SOURCE ONLY here. No Cloudflare or LIVE mutation is authorized.

## Current target

Fehler melden has one purpose:

POST /api/report -> coloring-pages-report-v1 -> Cloudflare Email Service EMAIL binding -> fixed project destination.

Canonical application provenance:

- coloring-pages commit 7f07c226105e26c0ca9cf91eb150a3e8f585c5ea
- Worker blob 50bbcd868aa9f91b7fb6d78a2925e867380ef421
- config blob 6ef838ec056c3815416e3a8521c5322bd33b4fed

Current config has two exact report routes and one send_email binding named EMAIL. The runtime contract pins local-part `INFO` on domain `ausmalwiese.de`; the uppercase local-part is the narrow reviewed Cloudflare workaround. The full destination remains only in the pinned coloring-pages config; Worker sender and all other behavior remain unchanged.

The exact Worker blob is also the source-of-truth for the sanitized Email Service failure diagnostic: fixed event `report_email_send_failed`, bounded machine code only, and `UNKNOWN` fallback. It must not log provider messages/stacks, report payload values, addresses, headers, IP or URL. This diagnostic is proven by exact source provenance; normal post-deploy verification does not generate an error or send an email.

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
5. the fixed destination from the pinned coloring-pages config, with local-part `INFO` on domain `ausmalwiese.de`, is accepted by Email Service;
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
