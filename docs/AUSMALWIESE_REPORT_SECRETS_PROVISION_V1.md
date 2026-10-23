# Ausmalwiese report Worker — private Wrangler secrets provisioner

**SOURCE ONLY. NOT INSTALLED. NO SECRET VALUES. NO LIVE.**

This source adds one minimal future owner-TTY helper for the already reviewed
`coloring-pages-report-v1` Wrangler deployment path. It does not install the
helper, create a secrets file, contact Cloudflare/Brevo/Turnstile, or deploy a
Worker.

## Fixed future paths

- installed helper: `/usr/local/sbin/rpi5-ausmalwiese-report-secrets-provision`
- protected directory: `/etc/rpi5-secrets/cloudflare` (must already be root-owned `0700`)
- one destination: `/etc/rpi5-secrets/cloudflare/ausmalwiese-report-wrangler-secrets.json`
- destination mode: root-owned `0600`, single link, exclusive create only

Never run the repository copy as root. A future separately authorized installer
must pin the merged helper bytes and install exactly that fixed executable.

## Interactive contract

A future separately authorized local foreground controlling TTY run prompts for
exactly four values, with terminal echo disabled for every prompt:

- `TURNSTILE_SITE_KEY`
- `TURNSTILE_SECRET`
- `BREVO_API_KEY`
- `REPORT_TO`

No value is accepted through command arguments, stdin, environment variables,
files supplied by the user, clipboard automation, browser state, or remote tool
output. The helper has no network client, subprocess execution, Wrangler call,
Cloudflare API call, token creation, mail send, deployment, retry, rollback, or
cleanup path.

The created JSON contains exactly those four names and is compatible with the
reviewed Wrangler `--secrets-file` flow. The helper prints only a sanitized PASS
status and never intentionally emits secret contents.

## Fail-closed behavior

Before prompting, the future installed helper requires:

- execution as root from the exact installed path;
- trusted root-owned non-writable path ancestry;
- installed helper mode `0500`, no hardlink/symlink;
- existing protected directory mode `0700`;
- destination absence, including symlinks.

Immediately before the one write it revalidates the protected directory inode
and destination absence. Creation uses `O_CREAT | O_EXCL | O_NOFOLLOW` and mode
`0600`, then `fsync` and metadata verification. Once the destination open/write
begins, any failure or ambiguity is terminal STOP. There is deliberately no
retry, overwrite, unlink, rollback, cleanup, alternate filename, or fallback
transport.

Python strings cannot guarantee memory zeroization. The implementation clears
the temporary bytearray used to collect TTY input after each prompt, but does
not claim hardened-memory secrecy.

## Remaining gates

Source merge does not authorize any runtime action. Before the report Worker can
be deployed, separate owner decisions are still required for:

1. installing the exact reviewed helper bytes on RPi5;
2. one interactive provisioning run that creates the protected secrets file;
3. the already reviewed bounded Wrangler deployment using that exact file;
4. read-only post-deploy verification.

Do not paste secret values into ChatGPT, GitHub, command arguments or logs.

## Offline acceptance

`python3 tests/test-ausmalwiese-report-secrets-provisioner-v1.py` uses only
synthetic values and mocked IO. It never reads `/dev/tty`, writes `/etc`, or
contacts external services. Tests cover exact four-field output, invalid values,
installed-path enforcement, controlling-TTY enforcement, echo restoration,
existing-target refusal, parent drift, exclusive `0600` one-shot creation,
confirmation gating and secret-free errors.
