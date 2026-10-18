# Ausmalwiese sitemap writer quiescence gate — SOURCE ONLY (#996)

This is a **proposed, not installed** read-only preflight for the separately
owner-authorized one-shot publication of the prepared `ausmalwiese.de` sitemap.
It does not publish, stop/start/disable any service, hold a persistent lock,
access secrets, or authorize any LIVE action.

## The actual blocker

The ingester and publisher both cooperate with the existing Drive-ingest
`.lock`, but `flock` is **advisory**. A successful `--check`, a root-owned
quiescence attestation, and the absence of a currently running ingester do NOT
prove an unrelated catalog writer cannot start later. The prior repeated
static cron/script audits were insufficient to close this race.

## Proposed bounded maintenance-window procedure (future owner gates)

1. Independently confirm and authorize a brief maintenance window. Under a
   **separate exact LIVE authorization**, stop only the fixed triggers:
   `cron.service` and
   the `rozkalns-simple-deployer` timer instance for `coloring-pages-public-rpi5`, first verify
   the `rozkalns-simple-deployer` service instance for `coloring-pages-public-rpi5` is idle.
   Stopping cron affects **other projects** and is never implicit. Never
   stop an active deployment or ingest job in this gate.
2. With those triggers stopped, verify the enabled post-publish marker and
   quiescence attestation are root-owned exact-content `0444` files; the
   originally installed publisher, generator and ingester are separately
   exact-blob-checked. The proposed `ausmalwiese-sitemap-writer-gate --check`
   rejects any active/unknown unit, altered marker, staged file or busy/changed
   lock. Its lock check releases its own descriptor without changing the file.
3. The gate's `BOUNDED_GATE_PASS` is **not independent proof of out-of-band
   writer exclusion**. An independently approved human/operator still must
   verify all Drive, external automation, Docker importer, post-ingest and
   catalogue writers cannot run throughout the publication. Any unclosed
   writer, active trigger or uncertain authorization is STOP before mutation.
4. Only a **new exact owner LIVE** authorization may invoke the already
   reviewed pinned publisher once, with a freshly checked catalog SHA-256 and
   previous sitemap SHA-256. The publisher itself reacquires the original
   nonblocking advisory lock and checks both hashes. After its first stage
   creation, every failure is STOP, without retry, rollback or cleanup.
5. After read-only local/public sitemap verification and separate assessment,
   restoring cron/timer operation requires **its own exact LIVE authorization**.
   This gate grants no restore, restart, deploy, Cloudflare or DNS authority.
   The `/q` Worker and final legacy-host 301 remain separate cutover gates.

## First-install-only installer source

The reviewed gate source is delivered together with a source-only installer at
`scripts/install-ausmalwiese-sitemap-writer-gate-v1.py`. It pins the gate's
executable Git blob `f189665fa7fbbe18f0b2ef748a7d6f588956fe91`, requires an
exact clean `RPi5_main/main` checkout, and targets only
`/usr/local/bin/ausmalwiese-sitemap-writer-gate` as root:root `0755`.
`--check` is read-only; `--apply` is first-install-only, uses O_EXCL/O_NOFOLLOW,
and never overwrites or repairs an existing path. After its first file creation,
any error is STOP with partial state preserved: no retry, rollback or cleanup.

The installer being merged is **not installation authority**. Executing either
root preflight or installation on RPi5 requires a separately explicit owner
LIVE/review authorization bound to the then-current exact `main` SHA. Installing
the gate also does not authorize stopping/restoring cron or deploy timers,
running the gate against LIVE state, or publishing the sitemap.

## Source contract / trust boundaries

Source file: `ops/bin/ausmalwiese-sitemap-writer-gate`.
Checks are fixed-path, fixed-unit and read-only; the only CLI is `--check`.
The gate rejects missing/nonregular/symlink markers, mismatched root ownership,
mode and content; non-idle/unknown systemd states; existing sitemap stage; and
busy/nonregular/replaced/mismatched Drive-ingest lock. It emits sanitized
`AUSMALWIESE_WRITER_GATE` JSON with no raw config, process args or secrets.

**This proposal is not installed or activated on RPi5.** Installing the gate,
stopping/restoring triggers, checking protected runtime and running a sitemap
publisher each require applicable, separately explicit owner authorizations.
No host file, service or state is changed by this PR. Offline tests use only
temporary directories and injected fake systemd unit readings.

### Limits deliberately not hidden

There is a small gap between this read-only gate's lock probe and the publisher
reacquiring its own lock; all actual catalogue writers MUST remain quiesced by
independent means. Stopping cron/timer alone is not a proof against manually
invoked or external writers. Keep a separately authorized maintenance window
and fail closed if anything starts or changes. There is **no automatic fallback**
to running publisher directly if this gate fails.
