# Hermes Deals Netto v2 — dedicated execution identity source contract

Status: **SOURCE-ONLY / EXECUTION DISABLED / HOST WIRING NOT AUTHORIZED**

Tracking:

- Phase 4 source work: `RPi5_main#425`;
- existing frozen helper binding: `RPi5_main#407` / PR #411;
- existing first-install contract: `docs/HERMES_DEALS_NETTO_NONROOT_PREFLIGHT_V2_INSTALLATION.md`;
- canonical residual-Hermes continuity: `RPi5_main#191`.

## Purpose

This source gate defines the execution identity that may eventually invoke the already-reviewed
Netto v2 read-only preflight helper. It does not create that identity, change host permissions,
wire a broker, invoke the helper, or authorize a canary.

The existing Hermes Deals origin-audit privileged broker/composition architecture remains the
pattern to reuse. This gate deliberately does not add a second socket, generic privileged command
broker, generic `sudo -u` surface, or caller-controlled process interface.

Machine-readable contract:
`ops/deploy/hermes-deals-netto-nonroot-preflight-v2-execution-identity.json`.

Source implementation:
`ops/lib/deploy_executor/hermes_deals_netto_nonroot_preflight_v2_execution_identity.py`.

## Frozen execution identity

The future child identity is source-fixed by account metadata, not by a caller-supplied UID:

- account: `hermes-netto-audit`;
- primary group: `hermes-netto-audit`;
- home: `/nonexistent`;
- shell: `/usr/sbin/nologin`;
- effective UID and GID: resolved from those exact fixed names and required to be non-zero;
- supplementary groups: exactly empty;
- forbidden execution accounts: `root`, `andris`, `github-runner`;
- forbidden group authority: `docker`;
- numeric UID/GID aliases to any present forbidden account/group are rejected.

The runtime validator fails closed if the account/group is absent, renamed, root, login-capable,
has a home directory different from `/nonexistent`, belongs to any supplementary group, aliases a
forbidden numeric UID/GID, or otherwise drifts from the fixed metadata. The historical `andris`
UID/GID 1000 shortcut is not this contract.

No user or group is created by this source change.

## Fixed privilege-drop process seam

The future root broker parent may only construct this process surface:

- interpreter: `/usr/bin/python3`;
- helper:
  `/usr/local/libexec/hermes-deals-audits/netto-missing-normal-price-nonroot-preflight-v2/netto_missing_normal_price_nonroot_preflight_v2.py`;
- argument: exact frozen registered Hermes source
  `067db7bd4b8057bc16a9bf0ef9ed8487127a0a05`;
- cwd: `/`;
- environment: fixed minimal `PATH`, `LANG`, `LC_ALL`, `PYTHONUNBUFFERED`;
- `shell=False`, `close_fds=True`;
- child `user`/`group`: numeric IDs obtained only from the validated fixed account/group;
- `extra_groups=()`;
- timeout: 50 seconds;
- stdout limit: 32768 bytes;
- stderr limit: 4096 bytes;
- invocation budget: one.

No GitHub issue, queue body, socket caller, adapter payload or helper output may select a command,
executable, path, argv, environment, UID, GID, supplementary group, cwd, shell, service or sudo
target.

Both the public launcher and its low-level process seam independently require all source activation
gates to be true before reaching account resolution or `subprocess.run`. In this source gate those
flags remain false: `execution_enabled=false`, `host_wiring_enabled=false`,
`access_evidence_resolver_wired=false` and `canary_authorized=false`.

## Authoritative helper and registration provenance

Before any later process launch, the source contract requires descriptor-safe verification of the
already-installed helper and registration:

- helper must remain a single-link regular non-symlink `root:root 0555` file;
- helper SHA-256 must remain
  `275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c`;
- registration must remain a single-link regular non-symlink `root:root 0444` file;
- registration SHA-256 must remain
  `887ad4e9295864307a24df6773e98f75056961aebeedd57b95641ba3e7386a1f`;
- registration bytes must equal the canonical frozen schema/capability/source/helper binding;
- path and opened descriptor identities must match.

This preserves the existing helper/registration trust root rather than replacing it with runtime
prose or caller-supplied provenance.

## Minimum fixed input-access contract

A future dedicated identity may receive only the access needed to reach the two reviewed input
surfaces. Public source represents the private host base as the neutral token `<owner-home>` and
source-fixes `owner_account=andris` plus every relative suffix. The exact absolute path remains
bound by the frozen reviewed helper provenance and, before any later host wiring, must be resolved
and revalidated by a separately reviewed trusted-host resolver. No caller may select or override the
base, account, or suffix.

The desired access evidence is exact and fail-closed:

| Relative path under `<owner-home>` | Type | Read/list | Traverse/execute | Write |
| --- | --- | --- | --- | --- |
| owner-home root | directory | no | yes | no |
| `hermes-deals-audits` | directory | no | yes | no |
| `hermes-deals-audits/netto-n9-visual-cell-validation-pack-v1-20260802T202304Z` | directory | no | yes | no |
| `.../generated` | directory | no | yes | no |
| `.../generated/fixture-manifest.json` | file | yes | no | no |
| `hermes-deals-netto-corpus` | directory | no | yes | no |
| `hermes-deals-netto-corpus/flyers` | directory | yes | yes | no |

The ellipses in this explanatory table are not implementation paths. The machine contract stores
the exact source-fixed relative suffixes plus the neutral owner-home token. Generic owner-home
read/list authority is explicitly forbidden.

This source gate does not decide how that minimum access will be realized. Absolute host-path
resolution, account creation, group membership, ACLs, ownership, `chmod`/`chown`, or another host
permission mechanism are separate later trust-boundary decisions and require fresh host evidence
and separate authorization where mutation is involved.

## Bounded sanitized result

The future launcher accepts only the frozen helper JSON schema and exact registered source/runner
identity. It rejects stderr, non-zero exit, unknown fields, identity drift, unexpected readiness
states, or any true mutation postcondition. Raw N9/corpus contents are never surfaced by this
contract.

The one-shot launcher consumes its in-memory invocation budget before the runner call. A failure
after that point does not produce an automatic retry, cleanup, rollback or alternate process path.

## Source-ready versus runtime-ready

Source-ready means only:

- dedicated identity/account metadata and numeric-alias rejection are fixed;
- helper and registration provenance gates are fixed;
- minimal input-access requirements are fixed as public-safe logical paths;
- privilege-drop argv/environment/resource bounds and low-level disabled gate are fixed;
- adversarial tests prove caller authority cannot widen those surfaces;
- the existing origin broker/composition pattern is named as the required architecture;
- every execution/host/canary flag remains false.

Runtime-ready is **not** established by merge. Before any host wiring, a later gate must freshly
revalidate current `RPi5_main/main`, exact-main CI, frozen Hermes provenance and trusted-host state,
then separately review the exact absolute-path resolver, account/group/access mechanism and broker
integration.

Any account/group/ACL/path-permission mutation or broker/service/socket installation is a separate
owner-authorized LIVE transaction. After that transaction, STOP and prove the installed identity,
no-Docker posture, minimum access, helper/registration provenance and wiring read-only.

A genuine Netto helper invocation/canary is another independent READY/LIVE-AUTH gate after host
wiring is proven. Runner retirement remains later and separately authorized.

Merge never authorizes LIVE.
