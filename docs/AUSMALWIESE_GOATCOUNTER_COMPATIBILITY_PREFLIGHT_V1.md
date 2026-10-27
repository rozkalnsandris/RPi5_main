# Ausmalwiese GoatCounter compatibility preflight v1 (#1266)

**SOURCE ONLY. NOT A LIVE AUTHORIZATION. NO INSTALL OR RUNTIME MUTATION.**

This contract defines the read-only gate between the successful pinned
GoatCounter v2.7.0 synthetic runtime proof and any future
install/database/service operation.

The canonical source operator is:

```text
scripts/ausmalwiese_goatcounter_compatibility_preflight_v1.py
```

A real execution on `rpi5` still requires a separate exact owner
authorization. Source merge alone does not authorize running the operator.

## Purpose

The future runtime design requires:

- service user/group `ausmalwiese-goatcounter`;
- service user/group `ausmalwiese-pageview`;
- private executable root
  `/usr/local/libexec/ausmalwiese-goatcounter-v1`;
- private database root `/var/lib/ausmalwiese-goatcounter`;
- private credential root `/etc/ausmalwiese-goatcounter`;
- exact unit names `ausmalwiese-goatcounter.service` and
  `ausmalwiese-goatcounter-pageview.service`;
- adapter listen port `127.0.0.1:9193`;
- GoatCounter listen port `127.0.0.1:9194`;
- existing catalog
  `/srv/coloring-pages-content/public/catalog.json`;
- systemd credential name `goatcounter-token`.

The preflight proves only whether those exact identities can be provisioned
without a detected conflict under the reviewed metadata-only rules. It does not
create or repair any of them.

## Source-first invariant

Before the first host metadata call, the operator validates the tracked source
contract:

1. exact
   `ops/contracts/ausmalwiese-goatcounter-pageview-v1.json`;
2. exact required service-unit lines for users, groups, paths, ports,
   `LoadCredential`, read/write boundaries and null stdout/stderr;
3. adapter source constants for the catalog, adapter listen address/port,
   backend URL and credential name.

Any source drift is:

```text
GOATCOUNTER_COMPATIBILITY=STOP CODE=SOURCE_CONTRACT_DRIFT
```

No host metadata is inspected after that failure.

## Host identity boundary

Only a non-root process on the intended host shape may continue:

- short hostname: `rpi5`;
- OS: `Linux`;
- architecture: `aarch64`;
- effective UID: non-zero.

The operator does not require or print a username.

## Exact account checks

Only these four NSS keys are queried:

- user `ausmalwiese-goatcounter`;
- user `ausmalwiese-pageview`;
- group `ausmalwiese-goatcounter`;
- group `ausmalwiese-pageview`.

The clean pre-install state is **ABSENT**. Any pre-existing exact identity is a
conflict because this gate does not inspect UID/GID history, shell, membership
or ownership provenance to declare a pre-existing account trustworthy.

The operator never enumerates passwd/group databases and never prints account
records.

## Target path checks

The following exact target roots must be absent:

```text
/usr/local/libexec/ausmalwiese-goatcounter-v1
/var/lib/ausmalwiese-goatcounter
/etc/ausmalwiese-goatcounter
```

Only `lstat(2)`-equivalent metadata is used. A pre-existing root is a
conflict regardless of type. The operator intentionally does not inspect its
contents. Root absence also proves that the reviewed binary/adapter, database
and credential child targets cannot already exist beneath that root.

No file is created, removed, renamed, opened for content, chmodded or chowned.

## Unit-name checks

For each exact unit name the operator runs only:

```text
/usr/bin/systemctl show --property=LoadState --value <exact-unit>
```

`not-found` is the only compatible pre-install state. Any other load state is
a conflict.

The operator never invokes `systemctl cat`, never reads installed unit files,
and never starts/stops/reloads/enables/disables a service.

## Exact port checks

Only ports `9193` and `9194` are queried, one at a time, with a kernel
socket filter:

```text
/usr/bin/ss -H -ltn "sport = :9193"
/usr/bin/ss -H -ltn "sport = :9194"
```

The command does not use `-p`; PID/process metadata is never requested.
Any listener returned for the exact port is a conflict. Listener output is
discarded and never copied to operator stdout.

The operator does not bind either port.

## Catalog metadata compatibility

The operator does not parse or read catalog contents. It checks only metadata
needed by the future unprivileged adapter:

- each resolved parent directory exists, is a directory and is traversable by
  an unrelated service identity (other-execute bit);
- the exact catalog path exists;
- the final catalog path is not a symlink;
- it is a regular file;
- size is between 1 byte and 8 MiB;
- it is other-readable;
- it is not other-writable.

Failure of any of those checks is fail-closed. This is only permission/path
compatibility evidence; the adapter itself retains the separate JSON/content
validation contract when it eventually runs.

## Forbidden inspection

The preflight never reads or prints:

- `/etc/ausmalwiese-goatcounter/pageview-token` contents;
- GoatCounter SQLite contents;
- process or container environments;
- process command lines or PIDs;
- raw private systemd/application configuration;
- unrelated socket/listener rows;
- unrelated users/groups;
- unrelated filesystem trees.

Tool errors and unexpected exceptions are reduced to fixed operator-safe codes.
Arbitrary exception text is never printed.

## Deterministic output

Success:

```text
GOATCOUNTER_COMPATIBILITY=PASS_READ_ONLY_COMPATIBILITY_SOURCE_ONLY USERS=ABSENT GROUPS=ABSENT TARGETS=ABSENT UNITS=ABSENT PORTS=FREE CATALOG=COMPATIBLE
```

Failure:

```text
GOATCOUNTER_COMPATIBILITY=STOP CODE=<reviewed-fixed-code>
```

Representative fixed code classes include source drift, host identity, exact
user/group conflicts, target-root conflicts, exact unit conflicts, exact port
conflicts, catalog metadata failures and metadata/tool unavailability.

Success does **not** authorize installation.

## Disconnected tests

```text
python3 tests/test-ausmalwiese-goatcounter-compatibility-preflight-v1.py
```

Tests use a synthetic source tree and fake host metadata only. They cover:

- clean absent/compatible state;
- source contract drift before any host metadata call;
- wrong host/OS/arch and root execution;
- each exact user/group conflict;
- each exact target-root conflict;
- both exact unit-name conflicts;
- both occupied exact ports;
- catalog missing/symlink/type/size/mode failures;
- catalog parent traversal failures;
- exact filtered `ss` argv with no process flag;
- exact `systemctl show LoadState` argv with no raw-unit read;
- tool failure sanitization;
- arbitrary exception-detail suppression.

## Runtime authorization boundary

After this source is merged, the next step is **not** installation. The next
gate is one separately owner-authorized read-only execution of this exact
preflight on `rpi5`, bound to the then-current exact Git SHA.

That future authorization does not imply:

- install or package authority;
- user/group creation;
- directory/file ownership or mode changes;
- credential creation or access;
- database creation or mutation;
- service lifecycle changes;
- port/network/Cloudflare changes;
- retry, rollback or cleanup.

Only a sanitized PASS can be used as evidence when designing a later exact
install/database/service authorization.
