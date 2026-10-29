# Private origin collector: source and rollout contract (#1274)

Status: source implementation; **not installed or activated** by this PR.
The owner selected ordinary origin detail-request counting. coloring-pages #419
records that decision; #424 implemented the tested Nginx candidate at immutable
commit `5a88082bcbdf97ee5280117c3eed3cf33a13db46`.

This outcome delivers the actual host-side collector, systemd socket/service
integration, executable startup guards, synthetic tests and this rollout plan.
It does not modify the installed browser adapter, GoatCounter backend, database,
retention, tunnel, application image/mounts or public measurement.

## Runtime boundary

`ausmalwiese-goatcounter-origin.socket` owns exactly
`/run/ausmalwiese-pageview/origin.sock`. systemd creates the dedicated parent
directory as root, mode 0755; the socket is mode 0660, owned by existing
`ausmalwiese-pageview:ausmalwiese-pageview`. A future application directory bind
is read-only and needs the resolved collector supplementary group. Read-only
filesystem access still permits the intended IPC writes. Never mount credentials,
the DB or a broad host directory into the application container.

systemd passes one listening AF_UNIX stream descriptor named `origin` as fd 3.
Startup rejects a wrong PID/fd count/name/type/path, non-listening socket,
incorrect owner/group/mode or unsafe parent directory. The collector never
creates/unlinks a socket, uses abstract ingress sockets, or binds a TCP listener.
systemd retains its descriptor across a service restart; stopping the socket
unit removes its path. Stop socket **and** service when disabling the channel.

`origin-peer.json` is a new non-secret, root-owned, non-group/world-writable file
in the root-managed executable directory. Its exact schema is
`{"schema":"ausmalwiese.origin-peer.v1","uid":<verified-host-uid>,"gid":<verified-host-primary-gid>}`.
Both IDs must be explicit positive integers; there is no guessed 101 default.
Derive the effective **host-mapped** UID/GID of the exact application process from
authorized metadata, including user-namespace mapping. Supplementary socket-group
access and the primary UID/GID peer check are separate requirements. Unknown,
ambiguous or unexpected mapping stops rollout. Matching Host/Origin headers are
never credentials; Linux `SO_PEERCRED` admission occurs before request parsing.

The socket group limits access to explicitly wired local processes. UID reuse,
other authorized group members and privileged host administrators remain part of
the host trust boundary; peer credentials are not a container identity service.

## Fixed protocol and limits

- Exactly `POST /internal/origin-count HTTP/1.0`, four distinct headers with fixed
  Host, JSON Content-Type, Content-Length 21 and Connection close, and exactly
  `{"page_id":"0123456"}` with seven ASCII digits. No query/Origin/cookie/auth/
  referrer/IP/UA fields, duplicate/folded/extra headers, chunking or keep-alive.
- Each connection can produce at most one count. Any extra bytes already read
  with the message are rejected; later pipelined requests cannot be processed
  because the connection is closed. This is not exactly-once delivery.
- Four admitted worker threads maximum, socket backlog eight, no unbounded work
  queue, 512-byte request-header cap and 200 ms total inbound receive deadline.
  Saturation drops immediately. The kernel may cap the backlog further.
- Current catalog is independently checked for valid shape, duplicate IDs,
  visibility and renderable single/multi-page entries. Parsing is serialized,
  limited to 8 MiB and cached by descriptor metadata. Atomic replacement changes
  inode identity; current read/validation failure never uses an older catalog.
  The sandbox preserves the **directory**, not a bind of one catalog inode.
- Only `no_sessions:true` and `/origin-detail-request/<id>` are generated for
  the existing loopback GoatCounter count API. No other caller bytes are copied.
- A fresh numeric loopback connection uses one send attempt and a 150 ms total
  backend I/O deadline. Only HTTP 202 is accepted. Redirect, connection error or
  uncertain response drops without retry. No DNS, proxy environment, raw event
  queue, retry spool or response-body buffering.
- Read-only catalog I/O and Python scheduling are not hard real-time guarantees.
  systemd additionally bounds CPU to 25%, memory to 192 MiB, tasks to 12 and fds
  to 64; shutdown is bounded to two seconds. Memory/CPU pressure may lose counts.

The process uses the existing count-only credential delivered by systemd's
`LoadCredential`; it does not provision a token or access SQLite. The credential
is read only at startup and never copied to source, arguments, responses or logs.
There is no request logging. Startup emits one fixed success/stop class in source
check mode; runtime stdout/stderr are disabled. No diagnostic exposes raw errors.

Type=notify marks startup ready only after source contract, non-root rpi5 service
identity, peer file, credential, current catalog and activated socket validate.
Readiness does **not** prove a count was durably stored or future retention
cleanup succeeded: startup sends no event. Restart=no and bounded systemd trigger/
start rates avoid a service retry loop. Operator recovery is separately scoped.

## Source artifacts and installation mapping

| Repository source | Exact future target | Owner/mode |
| --- | --- | --- |
| `scripts/ausmalwiese_goatcounter_origin_v1.py` | `/usr/local/libexec/ausmalwiese-goatcounter-v1/origin-collector.py` | root:root 0755 |
| `ops/contracts/ausmalwiese-goatcounter-origin-v1.json` | same directory, `origin-contract.json` | root:root 0644 |
| Authorized metadata-derived binding | same directory, `origin-peer.json` | root:root 0644 |
| `ops/systemd/ausmalwiese-goatcounter-origin.socket` | `/etc/systemd/system/ausmalwiese-goatcounter-origin.socket` | root:root 0644 |
| `ops/systemd/ausmalwiese-goatcounter-origin.service` | `/etc/systemd/system/ausmalwiese-goatcounter-origin.service` | root:root 0644 |

Freeze SHA-256 for all four source artifacts from the final merged Git SHA before
any host dispatch. Existing target files/units/path conflicts must be absent;
unexpected pre-existing files are drift, not overwrite permission. The existing
executable directory and every ancestor must be root-managed and non-writable
by the service. No new account, package, credential or database is required.

Public-source validation (no host identity, credential or catalog read):

```sh
python3 scripts/ausmalwiese_goatcounter_origin_v1.py --check-contract \
  --contract ops/contracts/ausmalwiese-goatcounter-origin-v1.json
python3 tests/test-ausmalwiese-goatcounter-origin-v1.py -v
```

`--serve` is a runtime operation. It is not a read-only preflight and must not be
used outside the installed service under fresh exact authority.

## One future private rollout envelope (not authorization)

1. Bind final source SHA/artifact hashes, host `rpi5`, the two new unit names,
   existing `ausmalwiese-goatcounter-pageview.service`, exact application target
   `coloring-pages-public-rpi5`, expected baseline and stop-on-failure behavior.
   Use Codex SSH as requested by the owner. All previous installation/retention
   permissions are consumed. Obtain separate authority before runtime work.
2. In the same bounded preflight, collect only authorized identity/mode/hash/
   service/port/socket facts: existing service account/group, installed binary/
   old unit hashes, active private backend and old adapter, new paths absent,
   safe parents, available systemd directives, and the exact application peer
   UID/GID mapping. No full Docker inspection/environment, raw protected config,
   credentials, DB, logs or backup reads. Protected mapping metadata needs to be
   named explicitly in the future authorization; source USER 101 is insufficient.
3. Materialize only the mapped files after all checks pass. Reuse the existing
   systemd credential source without opening it in the installer. No changes to
   backend unit, database, CollectNothing or native 365-day retention.
4. Stop and disable the superseded private TCP pageview adapter once. Install
   the two new units, daemon-reload once, enable/start the new socket and service,
   and wait for Type=notify readiness. Starting socket alone is insufficient.
   No automatic rollback/retry/cleanup on any post-mutation failure.
5. Verify fixed hashes/owner/modes, active/enabled state and socket identity, that
   TCP 9193 is absent and the existing backend remains loopback-only on 9194.
   No count POST or public detail GET is needed for this private install. Publish
   a sanitized receipt with exact identities and explicit verification limits.

The parent directory remains root-owned; the service does not need write access
to it because systemd owns the socket lifecycle. A service restart does not require
remounting an inode. A future socket stop/start recreates the inode in the same
directory. Such lifecycle operations still require their own exact authority.

The app is not wired by this private rollout. Its final config/image/read-only
directory bind and verified supplementary group are a separate app-source/runtime
change; public counting must wait for the actual-flow privacy/notice decision and
protected reporting. Once wired, ordinary live detail GETs may write counts and
must not be described as read-only verification. The old browser PR #391 and
public pageview tunnel route are not fallback paths.

## Test evidence and limits

Unit/transport tests use temporary Unix sockets, synthetic catalog files and an
ephemeral loopback mock backend. They exercise strict wire acceptance, exact peer
UID/GID denial, duplicates/extra headers/pipeline, total receive deadline, catalog
replacement/failure, saturation/recovery, single backend attempt, redirect/timeout
and token-injection rejection. Activation metadata and systemd source parsing are
checked without starting a system service.

The GitHub-hosted interop workflow checks out the immutable coloring-pages #424
transport proof and runs its actual pinned Nginx against this actual collector.
Only the catalog and final backend transport are synthetic; the real peer check,
worker limit, parser and generated backend payload run. Nginx has no external
network, no production mounts and no credentials. The fixture still proves the
original-query and error-log suppression fixes, permission denial, socket
replacement and failure/conditional-response semantics. It does not prove RPi5
UID mappings, installed systemd behavior, live data storage or legal clearance.

Official references:
[systemd socket units](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html),
[descriptor activation](https://www.freedesktop.org/software/systemd/man/latest/sd_listen_fds.html),
[Linux Unix sockets/SO_PEERCRED](https://man7.org/linux/man-pages/man7/unix.7.html),
[GoatCounter backend counting](https://www.goatcounter.com/help/backend).
