# Owner-authorized deploy executor v1 — P9 trusted evidence producers

Status: **SOURCE ONLY / DORMANT / NOT INSTALLED**
Roadmap: `RPi5_main#236`
Source gate: `RPi5_main#257`

This source gate adds narrowly typed producer and publisher contracts for the two P9 evidence objects already frozen by the merged semantic and provenance gates. It does not install or run a producer, inspect protected host state, enable the production executor registry, create READY/LIVE-AUTH state, or authorize a P9 canary.

## 1. Trust boundary

The unprivileged deploy executor must not be able to manufacture its own trust inputs. Therefore `p9_producer.py` is intended for a later separately reviewed root-owned producer boundary, while `p9_provenance.py` remains the unprivileged fixed-path consumer.

The producer API accepts typed observations only. It does not accept an arbitrary output path, arbitrary JSON object, command, shell fragment or argv. Publication is limited to the two merged filenames beneath `/run/rozkalns-deploy-executor-evidence`:

- `governance.json`
- `hermes-origin-baseline.json`

The publisher requires the already frozen root/service-group ownership and mode contract, creates an exclusive temporary file in the same directory, writes and `fsync`s the complete sanitized JSON object, then atomically replaces only the allowlisted target filename and `fsync`s the directory.

If atomic replacement fails, the source intentionally does not auto-retry or auto-clean the temporary evidence. A later live transaction must preserve the failure evidence and STOP under the normal mutation-error rule.

## 2. Governance evidence remains fail-closed

P0/P7 require a fresh authorization-repository writer-surface audit that covers all relevant ways an owner-created LIVE-AUTH issue could be modified. The producer therefore requires observations covering exactly:

- human collaborators;
- teams;
- installed Apps/integrations;
- workflow `GITHUB_TOKEN` permissions;
- explicit `issues: write` / `write-all` surfaces;
- token/secret-backed issue mutation paths.

Unknown writers, incomplete coverage, duplicate/invalid identities or repository identity drift are rejected before a digest is produced.

The canonical writer-set digest is deterministic over the normalized observed writer identities. However this source gate deliberately leaves `APPROVED_GOVERNANCE_WRITER_SET_SHA256 = None`.

That is a safety requirement, not an unfinished default. The available source/read capabilities in this gate do not establish the complete GitHub administration/writer surface. A later separately reviewed collector/audit capability must establish the complete writer set and a reviewed source change must pin the approved digest before `trusted=true` governance evidence can ever be emitted. No new GitHub admin credential or repository permission is invented by this gate.

Until that prerequisite is satisfied, governance evidence production fails closed and P9 cannot reach `DRY_RUN_READY` through this producer.

## 3. Hermes origin baseline derivation

The Hermes producer does not accept the six semantic safety booleans from a caller. It derives them from typed observations and emits the frozen booleans only after every reviewed identity check passes.

Frozen/current source identities for this gate are:

- repository: `rozkalnsandris/hermes-deals`;
- resolver: `hermes-deals.origin-path-registration.v1`;
- target: `hermes-deals-origin-path-audit`;
- installer source blob: `41f004420a0f5aed314aaefd796a54e14dbd17ea`;
- probe source blob: `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`;
- dispatcher source blob: `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`;
- current reviewed `origin-path-rpi5-audit.yml` workflow blob: `99a18c5f669e7880a8a8288c3f964285df87ae22`.

The workflow blob is point-in-time reviewed source identity, not permanent execution authority. If the Hermes workflow changes, producer source review must explicitly update the pin; runtime must not silently accept a new workflow identity.

The producer additionally requires the root registration's `registered_commit_sha` to equal an independently observed Hermes source commit SHA. The downstream P9 semantic resolver still independently binds the resulting `registered_commit_sha` to the exact owner-authorized LIVE-AUTH source SHA.

The six emitted assertions therefore mean:

- `registration_identity_ok`: resolver/target/source identity and reviewed installer source identity matched;
- `registered_source_match`: registration repository identity matched Hermes and the registered commit equaled the independently observed source commit;
- `probe_identity_ok`: reviewed probe source identity matched;
- `dispatcher_identity_ok`: reviewed dispatcher source identity matched;
- `workflow_identity_ok`: reviewed workflow source identity matched;
- `mutation_surface_read_only`: the observation contained no mutation class.

Any false condition fails before an evidence object is emitted.

## 4. Source-only acceptance tests

`tests/test-deploy-executor-p9-producer.py` covers:

- governance fails closed while the approved writer-set digest is unset;
- incomplete writer-surface coverage and unknown writers;
- duplicate/non-canonical writer identities;
- trusted governance output only for an exact source-approved digest;
- writer-set drift rejection;
- Hermes exact identity derivation for all six safety assertions;
- registration commit versus independent source commit mismatch;
- resolver/repository/installer/probe/dispatcher/workflow/mutation-surface drift;
- malformed source SHA rejection;
- fixed-file atomic publication and mode contract in a temporary fixture root;
- atomic replace failure preserving the temporary evidence instead of silently cleaning/retrying;
- root-only publisher boundary.

The suite is included in normal `make validate` and the deploy-executor Python modules remain covered by `py_compile`.

## 5. Explicit exclusions

This source gate does not authorize or perform:

- protected `/etc` or other protected-host inspection;
- evidence producer/spool/service installation or execution;
- credential/private-key placement or GitHub App permission/repository-settings changes;
- source-pin approval for a governance writer set without a complete reviewed audit;
- production registry activation;
- P8 poller, dispatcher or systemd mutation;
- READY or LIVE-AUTH creation/change;
- `adapter.apply()`, authorization consumption, root-helper invocation or result writing;
- production deployment, DB, Cloudflare, network, storage, Docker or runner mutation.

A later protected-host collector, root-owned producer/spool/service installation, any required credential capability, and any genuine P9 authorization canary remain separate Composite STRICT owner gates after their source contracts are reviewed and merged.

Merge of this source gate remains separately owner-authorized and would not authorize any live action.
