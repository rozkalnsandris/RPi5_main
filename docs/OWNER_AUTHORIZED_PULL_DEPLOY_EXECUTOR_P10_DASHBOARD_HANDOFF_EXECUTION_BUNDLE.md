# P10 Dashboard handoff execution bundle — source-only security contract

Status: **source only / execution disabled / no LIVE authority**. Issue: `RPi5_main#349`.

## Problem

The handoff materializer must eventually run as root, but `<fixed-owner-home>/RPi5_main` is an unprivileged writable Git checkout. Root must never execute/import Python from that checkout, `/tmp`, or the user-owned execution ingress.

## Reviewed source chain

The source repair binds these fixed capabilities:

- handoff wrapper `scripts/dashboard-rpi5-preverified-handoff-materializer.py`;
- unchanged handoff core `scripts/dashboard-rpi5-preverified-handoff-materializer-core.py`;
- existing unprivileged ingress preparer;
- unprivileged bootstrap emitter `scripts/dashboard-rpi5-handoff-execution-bootstrap-emitter.py`;
- unprivileged payload emitter `scripts/dashboard-rpi5-handoff-execution-payload-emitter.py`;
- root-only fixed receiver `scripts/dashboard-rpi5-handoff-execution-bundle-materializer.py`;
- unprivileged post-publication proof `scripts/dashboard-rpi5-handoff-execution-bundle-proof.py`.

The machine contract records each reviewed Git blob. The future merged main SHA/tree is deliberately obtained only after merge from fresh canonical GitHub state.

## Fixed unprivileged ingress

The reviewed ingress remains:

`<fixed-owner-home>/.cache/rozkalns-dashboard-handoff-exec-ingress/v1`

The `<fixed-owner-home>` prefix is resolved from the passwd database for fixed owner `andris`, not from caller input or `$HOME`. It is `andris:andris`, directory `0555`, files `0444`, and contains exactly the wrapper, core and `execution-manifest.json`. The manifest binds the fresh exact merged main SHA/tree plus both code Git blobs and SHA-256 digests.

The privileged side never opens this path.

## Bootstrap without root reading user paths

The bootstrap emitter runs unprivileged from a clean exact-main checkout. It proves that the bundle-materializer bytes equal the committed Git blob, then emits those bytes on stdout.

During the separately authorized execution-bundle LIVE gate those bytes may be written from stdin only to the fixed root-owned bootstrap destination:

`/var/lib/rozkalns-dashboard-handoff-exec/.bundle-materializer-v1.py`

The root process must not open the checkout or ingress as a source path. The bootstrap copy must be `root:root 0444` and its Git blob/SHA-256 must be read-only proven against the fresh merged source **before Python executes it**. Failure after the first root mutation preserves evidence; there is no automatic cleanup/retry/rollback.

## Fixed root receiver

After bootstrap proof, the only root receiver is the fixed root-owned file above. It accepts only:

`--apply --ack RPi5_main#349:MATERIALIZE-DASHBOARD-HANDOFF-EXECUTION-BUNDLE-V1`

and one bounded JSON payload on stdin. The unprivileged payload emitter constructs that payload only after descriptor-safe verification of the fixed ingress against clean exact local main/tree.

The root receiver hard-codes the reviewed wrapper/core Git blob identities, validates their SHA-256 values against the runtime manifest, and writes only:

`/var/lib/rozkalns-dashboard-handoff-exec/.v1.execution-bundle-partial`

It verifies root-owned destination bytes/modes/exact tree, then publishes with `renameat2(RENAME_NOREPLACE)` to:

`/var/lib/rozkalns-dashboard-handoff-exec/v1`

Final bundle directories are `root:root 0555`; wrapper/core/manifest are `root:root 0444`. After publication the absolute final path is reopened and reverified. The receiver does **not** invoke the handoff materializer.

## Runtime and gates

The only privileged handoff entrypoint is:

`/var/lib/rozkalns-dashboard-handoff-exec/v1/dashboard-rpi5-preverified-handoff-materializer.py`

That wrapper verifies its root-owned absolute bundle, exact tree, manifest, its own Git blob and the core Git blob **before importing the core**. Direct execution from the normal checkout fails closed.

Required order:

1. exact merged-source validation;
2. fixed candidate-ingress reproof;
3. unprivileged execution-ingress preparation/proof;
4. separate execution-bundle LIVE/root gate;
5. STOP + read-only execution-bundle proof against fresh merged main/tree;
6. fresh handoff-materialization LIVE/root gate;
7. STOP + read-only handoff proof;
8. only later candidate-stager/deploy gates.

`ops/deploy/executor-operations.json` remains globally `execution_enabled=false`. Source merge grants no LIVE authority. The previously granted handoff LIVE authorization is not reusable after #349.
