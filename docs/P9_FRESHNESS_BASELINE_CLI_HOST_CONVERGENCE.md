# P9 freshness baseline CLI host convergence contract

## Purpose

This source-only contract provides the missing capability-specific host convergence path after the P9 freshness-handoff repair merged in `RPi5_main#308`.

The repaired source exists in GitHub, but source merge does not prove or authorize trusted-host installation. The owner-observed RPi5 preflight showed that both the trusted checkout and the installed `/usr/local/sbin/rozkalns-deploy-p9-control-baseline` still carried the historical baseline CLI blob. The previously reviewed two-target source-repair operator is intentionally not reused because it can replace an additional P9 runtime source file and therefore exceeds this one-target gate.

Current P9 classification remains unchanged:

- `P9_EXIT_GATE=NOT_MET`
- `CLEAN_P9_REPEAT_REQUIRED=true`
- `P10_BLOCKED=true`

## Immutable target and provenance

This operator has exactly one host mutation target:

`/usr/local/sbin/rozkalns-deploy-p9-control-baseline`

Reviewed prestate:

- installed Git blob: `0afad9d93dd74570aeed31ccfdb8c5c7419ddcd8`;
- ownership: `root:root`;
- mode: `0755`;
- regular non-symlink file under a real root-owned, non-group/other-writable parent chain.

Reviewed repaired source:

- repository path: `ops/bin/rozkalns-deploy-p9-control-baseline`;
- Git blob: `8dc38e4d224373925483a45b782f04e0aa27a8bd`;
- semantics are the freshness-handoff repair merged by `RPi5_main#308`: 300-second evidence freshness is preserved, the operator-visible handoff metadata is derived from trusted GitHub server time after expensive collection, and publication/PASS is refused when fewer than 180 seconds remain.

The future operator invocation must bind an exact reviewed `RPi5_main` commit SHA. It reads replacement bytes only from that immutable commit via `git show <exact-sha>:ops/bin/rozkalns-deploy-p9-control-baseline` and independently requires those bytes to hash to the fixed repaired blob above.

## Fail-closed preflight

Before any host write, the operator must prove all of the following:

1. the supplied SHA is lowercase 40-hex and equals the checkout `HEAD`;
2. the operator file itself is unchanged relative to that exact SHA;
3. the process is root;
4. `O_NOFOLLOW` is available;
5. the reviewed repaired source object exists at the exact SHA and hashes to the fixed repaired blob;
6. every parent of the fixed target is a real directory, root-owned and not group/other writable;
7. the fixed installed target is a regular non-symlink file with `root:root 0755` metadata and the exact reviewed old blob.

For `--apply`, the complete preflight is performed a second time immediately before the mutation helper is entered.

Inside the mutation helper, the target is opened with `O_RDWR|O_CLOEXEC|O_NOFOLLOW`. Immediately before the first write it rechecks:

- opened-file regular-file type;
- `root:root 0755` metadata;
- exact reviewed old blob bytes;
- path regular/non-symlink type and metadata;
- path-versus-open-file `(st_dev, st_ino)` identity.

Any mismatch stops before the first write.

## Exactly one mutation

The first authorized mutation is the `ftruncate()` of the already-open fixed baseline CLI file. The operator then writes only the reviewed repaired bytes and `fsync()`s that same descriptor.

There is no path argument, target list, environment-selected target, glob, directory copy, generic command execution or second runtime target. Tests include a dynamic neighboring-file sentinel proving the replacement helper changes the selected baseline CLI file while leaving the sibling file byte-for-byte unchanged.

## Post-write verification

Before returning PASS, the still-open target must prove:

- metadata remains `root:root 0755`;
- installed bytes equal the reviewed immutable source bytes;
- installed Git blob equals `8dc38e4d224373925483a45b782f04e0aa27a8bd`.

A post-write verification error is a fail-closed terminal condition. There is deliberately no automatic retry, rollback, backup restoration, cleanup or alternate mutation path.

## Explicit non-events

This capability does not read, create, replace or mutate:

- `p9_source_auth.py` or any `/usr/local/lib/rozkalns-deploy-executor/` runtime file;
- P9 adapter, producer, collector, registry or `/etc/rozkalns-deploy-executor-p9/` configuration;
- systemd services or timers;
- credentials, private keys, tokens, permissions or GitHub App configuration;
- Cloudflare/D1 state or make any D1 request;
- baseline evidence or LIVE-AUTH issues;
- StateStore;
- P9 or P10 execution;
- dispatcher/result-writer/production mutation paths.

Source merge alone does not authorize `--apply` and does not prove trusted-host convergence.

## Future live gate

After this source capability is merged and the new exact `main` plus exact-main CI are revalidated, host convergence requires a separate STRICT LIVE owner authorization bound to that new exact SHA and this single target. The trusted checkout must first be converged to that exact SHA through an explicitly authorized reviewed source-update path if it is behind.

Only after successful host convergence and fresh post-write provenance evidence may a later, separately authorized clean P9 baseline/LIVE-AUTH/one-shot sequence be considered. P10 remains blocked until the clean P9 exit gate is actually satisfied.
