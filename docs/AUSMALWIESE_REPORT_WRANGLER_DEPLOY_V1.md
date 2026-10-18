# Ausmalwiese Report Worker — minimal Wrangler deploy contract (#1092)

SOURCE ONLY. No merge, LIVE deploy, Cloudflare mutation, credential access or email send is authorized by this document.

## Current application provenance

The canonical Report Worker application is owned by rozkalnsandris/coloring-pages:

- commit: 16c1ed5cccd43d28212b6a7aefbc04cae5195698
- Worker: cloudflare/report-worker.mjs
- Worker Git blob: 4ef00f9963c68ab9a4ab5aeb4a44b8c99c76eda0
- config: cloudflare/wrangler.report.json
- config Git blob: 2765e88f4c5ee7a01a5380ef52e4ff8c0688c9e6
- target Worker: coloring-pages-report-v1
- Wrangler: 4.135.0

The reviewed config contains only two exact routes:

- ausmalwiese.de/api/report
- www.ausmalwiese.de/api/report

and one Cloudflare Email Service send_email binding:

- name: EMAIL
- destination_address: info@ausmalwiese.de

There are no Report secrets, Turnstile bindings, rate-limit bindings, Report config endpoint or Stats dependency.

## One-shot deploy shape

The future deploy command is limited to the exact reviewed application/config plus provenance tag/message. It does not use --secrets-file, vars, D1, generic routes or secret commands.

The root-owned installed entrypoint remains:

/usr/local/sbin/rpi5-ausmalwiese-report-wrangler-deploy

The installed file is only a trust boundary. Runtime execution drops the Wrangler child to the fixed operator andris and uses that operator's existing Wrangler authentication context. It reads no protected Report secret file and creates no secret memfd.

The runtime installer is repinned so a future separately authorized upgrade may replace the currently reviewed installed runtime blob 55b13636ba36cdc574fedbeb469c73af91bb8594 with the #1092 minimal runtime bytes. Source merge does not install it.

## Read-only post-deploy proof

Minimum evidence after a separately authorized deploy:

- latest Report version and exactly one active version at 100%;
- exact source/config provenance from Script/Version Settings annotations;
- exactly the two report routes;
- exactly one binding kind: EMAIL = send_email.

The bounded read plan uses versions list, deployments list, versions view and one Script/Version Settings annotations read. It does not require secret list, /api/report/config or any Stats snapshot.

Mailbox delivery is a separate end-to-end check after LIVE activation.

## Provider model

Cloudflare Email Service documentation reviewed 2026-10-18 documents a send_email Wrangler binding and env.EMAIL.send(). destination_address restricts the binding to one configured destination; a send call may use null/undefined recipient to select that configured destination.

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
