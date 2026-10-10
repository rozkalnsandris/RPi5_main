# SIMPLE-DEPLOY per-target systemd timer templates — CV-first (#103)

**Status: SOURCE-ONLY / NOT INSTALLED / NOT ACTIVATED.** This design adds two inert source files. It does not install units, reload systemd, enable/start timers, invoke Docker or deploy anything. Merging the PR grants no LIVE authority. The existing five-target `rozkalns-simple-deployer.service` and `.timer` stay unchanged and their timer must remain disabled/inactive during any future CV-only activation.

## Reuse the existing host executor

The new paired templates are:

- `ops/systemd/rozkalns-simple-deployer@.service`
- `ops/systemd/rozkalns-simple-deployer@.timer`

The service retains the **exact existing generic service sandbox/principal and fixed executable**, changing only the description and argument from `--all` to `--target %i`. `%i` is the systemd escaped instance identifier, passed as one argument without a shell. The existing executor validates the exact instance against the installed, root-reviewed static target registry; unknown or altered instances fail closed. The templates accept no runtime path, image, Compose, URL, shell, or repository input.

The template timer's `Unit=rozkalns-simple-deployer@%i.service` selects one matching instance; it has no `DefaultInstance` and does not enable anything by itself. Its fixed monotonic `OnActiveSec=2min` and `OnUnitInactiveSec=2min` schedule avoids the existing global timer's `OnBootSec`/`Persistent` coupling. **Do not assume a two-minute grace period**: after a previous instance service execution, an elapsed `OnUnitInactiveSec` can make activation due immediately. Treat activation as potentially mutating before any subsequent operator step. Repeated pre-mutation failures under a standing timer must be investigated; no ad-hoc retry, rollback, or alternate path is permitted after an unexpected LIVE mutation.

This is not a new deployment framework, installer, controller, webhook, or GitHub Actions workflow. Immutable GHCR digest comparison, per-target locking, Compose, health/readiness and receipt semantics remain entirely with the existing `simple_deploy_v1.py`. A target with an unchanged accepted digest is `NO_OP_CURRENT`.

## CV first; no other implicit activation

Only the following first instance is proposed for **a later, separately authorized** installer/activation step:

`rozkalns-simple-deployer@` + `rozkalns-cv-rpi5` + `.timer`

Its service is `rozkalns-simple-deployer@` + `rozkalns-cv-rpi5` + `.service`, and its executor target is `rozkalns-cv-rpi5`. This target already has a successfully verified one-shot SIMPLE-DEPLOY receipt; that historical evidence is not a future release or timer authorization. **No Weather, Coloring Pages, Hermes Deals or Hermes Tech instance is approved for installation or activation by this source PR.** Their adoption and GitHub-side publication triggers remain distinct future decisions. The legacy CV pull-deploy timer also stays disabled.

## Required separate CV activation gate — later, not executed here

Before even installing units, review a fresh exact-main and installed-host snapshot and obtain a new exact owner LIVE authorization that freezes the unit bytes and only the two root-owned template destinations plus the CV instance. Minimum fail-closed preflight:

1. Prove exact `RPi5_main/main`, reviewed service/timer template SHA-256, installed executor/registry/Compose identities and the same `rozkalns-simple-deployer` UID/GID/sandbox; no unreviewed symlink, unit override, or conflicting existing instance.
2. Prove CV `main`, successful exact-source GitHub publication, anonymous GHCR arm64 source/shared-workflow labels and immutable index digest; compare it with the running image and accepted last-success receipt. Unknown/stale/pending candidate or overlapping publication means STOP. Any necessary one-shot CV reconcile needs separate authorization before activation.
3. Prove CV liveness/readiness HTTP 200, valid non-blocked target status/receipt, no unresolved `STOP_ERROR` or in-flight mutation, generic `--all` timer disabled/inactive and no queued `--all` service job; no legacy CV pull-deploy timer; no competing CV instance job. The generic `--all` service must never run concurrently with the per-target schedule.
4. Review the standing authorization risk: activating the CV timer permits **future** ordinary CV application image pulls and Compose updates without per-release owner commands. Explicitly bind that risk, timing and failure semantics in the new LIVE decision; preflight must precede `enable/start` because the first tick may occur immediately.
5. Install only exact fixed reviewed service/timer templates, reload systemd and enable/start **only** `rozkalns-simple-deployer@` + `rozkalns-cv-rpi5` + `.timer` once under that authorization. Verify timer enabled/active, expected target service, health/readiness and immutable digest receipt. Any error/drift after the first write means evidence + STOP, with no retry/rollback/cleanup by default.

The existing five-target timer restoration contract and all nine gates in `docs/SIMPLE_DEPLOY_TIMER_RESTORATION_V1.md` are unchanged. This **per-target source design does not declare `--all` safe to activate**, shrink the static registry, activate Hermes, or establish Weather/Coloring publication cadence. No production secrets/config, protected data, systemd/Docker state or Cloudflare changes belong in this PR.

Documentation: [systemd template instances](https://man7.org/linux/man-pages/man5/systemd.unit.5.html), [monotonic timer semantics](https://man7.org/linux/man-pages/man5/systemd.timer.5.html).

**Production deploy/change REQUIRED: NO** for this source-only PR. Subsequent CV timer installation/activation: **YES, separate exact owner LIVE gate**.
