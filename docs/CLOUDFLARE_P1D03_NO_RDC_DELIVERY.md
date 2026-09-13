# Cloudflare P1D-03 no-RDC GET-only delivery

Issue: `#519`  
Parent lane: `#179`

This source defines a GitHub-hosted delivery path for the existing P1D-03 browser SSO preflight. It exists so the canonical raw Cloudflare API evidence can be collected without Lenovo/RDC or an RPi5 checkout.

## Security boundary

The delivery path is read-only by construction:

- the Cloudflare client is the existing `CloudflareGetClient`, whose public operation is HTTP `GET` only;
- the workflow has GitHub `contents: read` and `actions: read` permissions only;
- no Cloudflare write token is accepted;
- no generic Cloudflare URL, HTTP method or command input is accepted;
- API-base overrides are rejected in GitHub Actions;
- workflow reruns are rejected;
- checkout credentials are not persisted;
- no GitHub result comment or other GitHub write is performed;
- no secret provisioning is authorized by merging this source.

The workflow accepts only dedicated secret names:

- `CLOUDFLARE_P1D03_ACCOUNT_ID`
- `CLOUDFLARE_P1D03_READ_API_TOKEN`
- `CLOUDFLARE_P1D03_OWNER_EMAIL`

Secret values must never be printed, committed, pasted into issue comments, or otherwise published.

## Owner trigger

The workflow exists on the default branch and listens for a newly created issue comment on canonical issue `#179`. The comment must be authored directly by the repository owner (`type=User`, numeric owner ID bound in source, `author_association=OWNER`) and must not be GitHub-App-authored.

Exact command contract:

```text
/rpi5-p1d03 check HEAD=<exact-main-sha> CANARY=p1d-03-browser-sso-preflight
```

The command SHA must equal the `issue_comment` event's default-branch SHA. Before the first Cloudflare GET, the adapter also proves that the SHA is still current `main` and that exact-main push runs for `Validate`, `FAST-LANE policy drift`, and `GITHUB-ONLY policy drift` all completed successfully.

## Evidence semantics

P1D-03 performs only these Cloudflare API reads through the existing preflight implementation:

1. token verification;
2. Access Organization read;
3. Access applications read;
4. Access policies read for discovered applications.

The sanitized report does not emit the owner email, account ID, auth/team domain, app or policy IDs, AUD, cookie/JWT, or API token. An omitted Organization `session_duration` is interpreted by the existing contract as Cloudflare's documented effective `24h` default; an invalid present value blocks.

A P1D-03 PASS is evidence only. It does not authorize P1D-04. If `change_required=true`, the next step remains a separate P1D-04 credential/LIVE authorization boundary.
