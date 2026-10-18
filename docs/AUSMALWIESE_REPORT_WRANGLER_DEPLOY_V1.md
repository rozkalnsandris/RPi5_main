# Ausmalwiese Report Worker — minimal Wrangler deploy contract (#1098)

SOURCE ONLY. No merge, LIVE deploy, Cloudflare mutation, credential access or email send is authorized by this document.

## Current application provenance

The canonical Report Worker application is owned by rozkalnsandris/coloring-pages:

- commit: 7f07c226105e26c0ca9cf91eb150a3e8f585c5ea
- Worker: cloudflare/report-worker.mjs
- Worker Git blob: 50bbcd868aa9f91b7fb6d78a2925e867380ef421
- config: cloudflare/wrangler.report.json
- config Git blob: 6ef838ec056c3815416e3a8521c5322bd33b4fed
- target Worker: coloring-pages-report-v1
- Wrangler: 4.135.0

The reviewed config contains only two exact routes:

- ausmalwiese.de/api/report
- www.ausmalwiese.de/api/report

and one Cloudflare Email Service send_email binding:

- name: EMAIL
- destination local-part: `INFO`
- destination domain: `ausmalwiese.de`

The runtime contract assembles those fixed components with `@` and rejects lowercase local-part drift.

There are no Report secrets, Turnstile bindings, rate-limit bindings, Report config endpoint or Stats dependency.

The exact reviewed Worker blob also carries the privacy-bounded send-failure diagnostic contract: one structured event `report_email_send_failed`, a bounded machine `code` matching `E_[A-Z0-9_]+`, and `UNKNOWN` fallback. Provider messages/stacks and visitor/request-derived fields are outside that log contract.

## One-shot deploy shape

The future deploy command is limited to the exact reviewed application/config plus provenance tag/message. It does not use --secrets-file, vars, D1, generic routes or secret commands.

The root-owned installed entrypoint remains:

/usr/local/sbin/rpi5-ausmalwiese-report-wrangler-deploy

The installed file is only a trust boundary. Runtime execution drops the Wrangler child to the fixed operator andris and uses that operator's existing Wrangler authentication context. It reads no protected Report secret file and creates no secret memfd.

The runtime installer is repinned so a future separately authorized upgrade may replace the currently reviewed deploy source from RPi5_main 4baa94b39264c8a89c175f3fdefdfe78faa5b339 / blob 6a5b15e121bbca41b6b33582bcc62964df723927 with the #1098 deploy source blob b960b752ab5b91594b174f06fb66da4e62806be8. Source merge does not install it.

## Read-only post-deploy proof

Minimum evidence after a separately authorized deploy:

- latest Report version and exactly one active version at 100%;
- exact source/config provenance from Script/Version Settings annotations;
- exactly the two report routes;
- exactly one binding kind: EMAIL = send_email;
- exact Worker-blob provenance for the sanitized send-failure diagnostic; no log generation or test email is required by post-deploy verification.

The bounded read plan uses versions list, deployments list, versions view and one Script/Version Settings annotations read. It does not require secret list, /api/report/config or any Stats snapshot.

Mailbox delivery is a separate end-to-end check after LIVE activation.

## Provider model

Cloudflare Email Service documentation reviewed 2026-10-18 documents a send_email Wrangler binding and env.EMAIL.send(). destination_address restricts the binding to one configured destination. This repin additionally enforces local-part `INFO` on domain `ausmalwiese.de`; lowercase local-part `info` is rejected by the runtime contract. The full destination value remains only in the pinned coloring-pages config. The Worker sender remains unchanged.

References:

- https://developers.cloudflare.com/email-service/api/send-emails/workers-api/
- https://developers.cloudflare.com/email-service/configuration/send-bindings/
- https://developers.cloudflare.com/workers/wrangler/configuration/

## Offline checks

python3 scripts/ausmalwiese_report_wrangler_deploy_v1.py --check-contract
python3 tests/test-ausmalwiese-report-wrangler-deploy-v1.py
python3 tests/test-ausmalwiese-report-wrangler-runtime-boundary-v1.py
python3 tests/test-ausmalwiese-report-wrangler-verify-v2.py

Passing source checks is not LIVE evidence.
