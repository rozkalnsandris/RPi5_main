# Hermes SIMPLE-DEPLOY host-prerequisite materialization v2

Issue: `#713`  
Status: **SOURCE CORRECTION READY / NOT LIVE**

## Why v2 exists

The v1 source contract from #711/#712 incorrectly modeled `/var/lib/rozkalns-simple-deployer` as `root:root 0755`.

Fresh read-only production evidence showed that directory is owned by the SIMPLE-DEPLOY runtime principal and has mode `0700`. The generic installer confirms this is the intended Phase-B security boundary: it creates `/var/lib/rozkalns-simple-deployer` and its Phase-B runtime child with the fixed `rozkalns-simple-deployer` user/group and mode `0700`.

Therefore the production host is not drifted. The v1 parent model is superseded by this v2 correction. Production must **not** be repaired with `chown`/`chmod` to match v1.

## Canonical Phase-B state parent

The parent is fixed as:

- path: `/var/lib/rozkalns-simple-deployer`;
- owner user: `rozkalns-simple-deployer`;
- owner group: `rozkalns-simple-deployer`;
- mode: `0700`;
- it must already exist before Hermes prerequisite materialization;
- the Hermes materializer may not create, re-own or relax this parent.

Numeric UID/GID values are deliberately not stored in source. They are resolved from the fixed runtime user/group and validated against the existing principal metadata.

The generic installer and accepted Weather canary remain unchanged.

## Consequence for public-safe preflight

A normal `andris` process can `lstat` the Phase-B parent itself, but mode `0700` intentionally prevents that account from traversing the runtime-owned directory. Therefore an unprivileged process cannot truthfully determine whether fixed Hermes child destinations or staging paths are present.

v2 never interprets that access denial as absence.

The classifier has four states:

- `ABSENT`: all fixed child destinations were actually observed absent and the required parents have exact metadata;
- `EXACT_READY`: all fixed destinations were actually observed with the reviewed metadata/shape;
- `PARTIAL_CONFLICT`: observable state conflicts with the contract;
- `PRIVILEGED_METADATA_REQUIRED`: the current account lacks permission to observe required child metadata.

`PRIVILEGED_METADATA_REQUIRED` is a non-success state. It grants no privilege escalation and does not imply LIVE authority.

A future privileged metadata-only preflight may be performed only under a separate owner decision. It is still non-mutating and must not read `.env` values, application data contents or configuration contents.

## Source identity

The fixed Hermes source identity remains unchanged:

- source account: `andris`;
- checkout relative to passwd-resolved home: `hermes-deals`;
- data: `data/raw`;
- config: `config`;
- protected env: `.env`.

No concrete user-home path, numeric production runtime UID/GID, caller-selected path, repository, env file, key, command, Docker service or systemd unit is accepted by the CLI.

## Fixed materialized destinations

The Hermes destinations remain:

- state root: `/var/lib/rozkalns-simple-deployer/hermes-deals`;
- data: `/var/lib/rozkalns-simple-deployer/hermes-deals/data/raw`;
- config: `/var/lib/rozkalns-simple-deployer/hermes-deals/config`;
- private env: `/etc/rozkalns-simple-deployer/private/hermes-deals-api.env`.

Materialized Hermes state children stay normalized as `root:root` directories/files under the runtime-owned Phase-B parent. The private env remains `root:root 0600` under a `root:root 0700` private namespace.

This child ownership does not require changing the Phase-B parent: the fixed runtime user owns the `0700` parent and can traverse it; reviewed child directories are `0755`.

## Protected apply boundary

`--apply` remains future LIVE-only.

v2 reuses the already-reviewed v1 protected parsing/copy/digest helpers, but replaces the parent/preflight/publication orchestration so that:

1. the Phase-B state parent must already be exact runtime-user/runtime-group `0700`;
2. it is never created, re-owned or chmodded by the Hermes materializer;
3. protected materialization starts only after an exact privileged `ABSENT` classification;
4. the private namespace may be created as `root:root 0700` inside the separately authorized apply;
5. staging beneath the Phase-B parent remains operation-specific and root-owned;
6. state publication and private-env publication remain no-overwrite operations;
7. protected values are never emitted;
8. no automatic retry, rollback or failure cleanup is added.

A post-mutation failure still stops with evidence in place.

## Tests

The focused v2 suite locks:

- runtime-principal `0700` Phase-B parent semantics;
- symbolic runtime identity instead of production numeric UID/GID;
- `PermissionError` is `INACCESSIBLE`, never `ABSENT`;
- hidden child state returns `PRIVILEGED_METADATA_REQUIRED`;
- protected values remain unread/unemitted in public preflight;
- apply preserves existing Phase-B parent metadata;
- missing/drifted Phase-B parent fails before materialization;
- post-mutation failure preserves evidence;
- the generic Phase-B installer remains unchanged;
- CLI authority remains limited to `--expected-source-sha` and `--apply`.

CI uses synthetic fixtures only. It performs no RPi5 access and invokes no `--apply`.

## Authority

#713 is source/docs/tests/CI only.

It authorizes none of the following:

- host filesystem mutation;
- sudo/root execution;
- privileged host metadata inspection;
- `.env` value or application data/config content reads;
- secret copy/write;
- Hermes target adoption;
- Docker or systemd actions;
- database/schema/data-plane actions;
- network or Cloudflare changes.

After merge and exact-main green, the next gate is a separately authorized **privileged read-only metadata preflight** against the fixed v2 classifier. Only after that succeeds can a distinct Composite LIVE materialization/adoption/reconcile decision be considered.
