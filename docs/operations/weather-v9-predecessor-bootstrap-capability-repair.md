# Weather v9 predecessor-bootstrap installed capability repair

Issue: #634

## Why this repair exists

The first installed predecessor-bootstrap capability was built from
`RPi5_main@7beb7da3908b3f74ffc96cba6297402523096c2b`. Its first root-broker
read-only preflight failed during Python package import before predecessor
validation. Issue #632 / PR #633 fixed that broker import closure.

The first-install capability installer cannot be reused for this host state:
it deliberately requires the capability/config/replay/systemd targets to be
absent and creates them exclusively. The installed capability must therefore
be repaired in place through a narrower, separately reviewed path rather than
deleted, cleaned up, or reinstalled.

## Fixed predecessor and target

The repair accepts only the installed predecessor broker SHA-256:

`4e484763444027ded541429944ae5a1ebacd3beaf81b00198c7be07954fa2676`

The corrected broker source must have SHA-256:

`f7bcf225166fe1598139abbbaf26c713b81170ef49ccbd94b32d046957c4a892`

The repair source SHA itself is not guessed in source. It is derived from the
clean detached trusted repair checkout at execution time and must later be
bound to the exact merged `RPi5_main` commit by the owner LIVE gate.

## Read-only preflight

The default invocation performs a root read-only preflight. Root is required
because the capability registration lives below a root-owned `0700` directory.

Preflight fails closed unless all of the following are true:

- the repair runs from the fixed dedicated trusted source checkout;
- that checkout is detached, clean, linked to the canonical manager Git
  directory, and has the reviewed origin;
- registration is schema v1 and binds predecessor source
  `7beb7da3908b3f74ffc96cba6297402523096c2b`;
- installed broker is exactly the predecessor hash above;
- the eight other installed release files are byte-identical between the
  predecessor source, target source, and installed release;
- socket/service unit bytes and registration hashes are unchanged;
- capability/release/config/replay directory ownership and modes are intact;
- no repair temp path already exists.

The preflight reads only replay-root directory metadata. It does not read,
rewrite, consume, remove, or reset replay state.

## Apply boundary

`--apply` requires a separate exact owner LIVE authorization. Source merge
does not authorize it.

The complete mutation budget is exactly two atomic replacement operations, in
this order:

1. `/etc/rozkalns-weather-v9-predecessor-bootstrap/registration.json`
   (`root:root 0600`);
2. `/usr/local/libexec/rozkalns-weather-v9-predecessor-bootstrap/current/ops/bin/rozkalns-weather-v9-predecessor-bootstrap-broker`
   (`root:root 0755`).

Registration is written first. Until the broker replacement completes, any
request sees a release-hash mismatch and fails closed rather than executing a
partially repaired capability.

There is no `systemctl` call, daemon reload, socket restart, replay mutation,
other release-file replacement, predecessor bootstrap apply, Weather runtime
mutation, permission relaxation, generic root shell, automatic retry, cleanup,
or rollback.

If an error occurs after mutation begins, preserve the observed state and
STOP. Do not rerun the repair or remove a temp file without a fresh exact
owner recovery authorization.

## Later LIVE sequence

After this source change is merged:

1. materialize the exact merged `RPi5_main` SHA in the fixed detached trusted
   repair checkout under a separate bounded source-delivery authorization;
2. owner-interactively run the default repair entrypoint as root for the
   read-only preflight;
3. if and only if that preflight passes, obtain a separate exact LIVE repair
   authorization and run one `--apply`;
4. verify the repaired broker + registration closure read-only and confirm
   the socket remains enabled/active without changing systemd;
5. submit one new root-broker `preflight` request. This is not a retry of the
   failed predecessor binary; it executes the newly repaired broker;
6. only if that preflight passes, create a fresh predecessor-bootstrap `apply`
   authorization and continue the existing recovery runbook.

No step in this document authorizes production Weather DB/corpus mutation,
Docker/application replacement, Cloudflare/network changes, secrets, or
permissions.
