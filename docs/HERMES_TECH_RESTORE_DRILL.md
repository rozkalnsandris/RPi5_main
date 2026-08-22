# Hermes Tech retained-backup restore drill

This document defines the RPi5-owned operator for `rozkalnsandris/hermes-tech#90`
and `RPi5_main#117`. It complements the application acceptance contract in
Hermes Tech `docs/restore-drill.md`; it does not replace the encrypted backup
producer in `ops/bin/rpi5-backup`.

## Scope

`ops/bin/hermes-tech-restore-drill` is a **manual, fail-closed operator** for one
already-retained local encrypted V12 backup and its matching `.sha256` sidecar.
It does not fetch from Google Drive, alter retention, schedule itself, restart a
service, deploy Hermes Tech, write the live database, or change credentials.

The first real retained-backup run is a separate host authorization gate after
this source is reviewed, merged, and the exact merged SHA is selected.

## Preconditions

Before a real drill, resolve and record without printing secret material:

- the exact retained `rpi5_backup_YYYY-MM-DD_HH-MM-SS.tar.gz.age` path;
- its matching `.sha256` sidecar;
- the configured `AGE_KEY` identity path used by the V12 backup owner;
- the exact current Hermes Tech production application root;
- the exact reviewed `RPi5_main` source SHA containing this operator;
- the exact reviewed Hermes Tech source SHA containing
  `tools/verify_restore_root.py`;
- a private local work filesystem with sufficient free space;
- an evidence output path outside the temporary restore root.

The production application root is an explicit runtime input. It must resolve to
an existing absolute directory, is not written into evidence, and is used both
to derive the exact archive subtree and to keep work/evidence/restore targets
outside production. No concrete host user-home path is stored in this public
repository.

The age identity must be a regular file with no group/other permission bits.
Its contents are never read by this operator; they are passed only to `age` as
an identity file.

## Fail-closed sequence

The operator performs the following order:

1. validate the explicit production application root and derive its archive
   subtree without recording the root in evidence;
2. validate the backup filename and verify the exact sidecar SHA-256 before
   decryption;
3. verify the RPi5 operator and Hermes verifier are clean files from the exact
   requested Git SHAs;
4. require a non-production work directory and a conservative free-space
   preflight;
5. create a fresh `0700` workspace and decrypt to a temporary `0600` tarball;
6. validate the whole archive, then re-check free space against the declared
   Hermes regular-file sizes before materialization; reject duplicate,
   absolute or `..` paths, devices/FIFOs, unsupported entry types and escaping
   symlink/hardlink targets;
7. require the V12 metadata manifest plus the complete Hermes restore shape;
8. extract **only** the archive subtree corresponding to the explicit
   production application root into the isolated restore root;
9. invoke the reviewed Hermes `tools/verify_restore_root.py` from the exact
   source SHA;
10. retain only a bounded sanitized verifier summary;
11. remove the whole plaintext workspace on success or failure;
12. write the final evidence only after cleanup has been attempted. A cleanup
    failure converts the drill to FAIL.

The backup `created_at` timestamp is read only from
`backup-metadata/manifest.txt`; hostname, kernel and remote-storage fields from
that manifest are not copied into drill evidence.

## Evidence contract

The final JSON is mode `0600` and contains only:

- backup basename and manifest timestamp;
- encrypted archive SHA-256 and size;
- reviewed RPi5 and Hermes source SHAs;
- start/end timestamps and elapsed seconds;
- a bounded verifier summary (Git HEAD/fsck, SQLite hash/size/quick-check/schema
  and unchanged flag, `.env` mode with `contents_read=false`, Hugo output sizes);
- PASS/FAIL, sanitized failure category and plaintext-cleanup result.

It must not contain the production application root, age identity path or bytes,
`.env` values, article/DB rows, retained archive plaintext, visitor data,
remote-storage identifiers, full restore paths, tokens or credentials.

## Example command shape

The values below are placeholders. Resolve exact current SHAs, the current
production application root, and the selected retained archive at execution
time; do not copy historical values from an issue or chat.

```bash
sudo python3 ./ops/bin/hermes-tech-restore-drill \
  --archive /opt/backups/rpi5_backup_YYYY-MM-DD_HH-MM-SS.tar.gz.age \
  --age-identity /path/from/current-rpi5-backup-config/age.key \
  --production-app-root /srv/example/hermes-tech \
  --rpi-source-root /path/to/reviewed/RPi5_main \
  --rpi-source-sha <EXACT_40_HEX_RPI5_MAIN_SHA> \
  --hermes-source-root /path/to/reviewed/hermes-tech \
  --hermes-source-sha <EXACT_40_HEX_HERMES_SHA> \
  --evidence /var/tmp/hermes-tech-restore-drill-YYYYMMDDTHHMMSSZ.json
```

The sidecar defaults to `<archive>.sha256`. The default work base is `/var/tmp`;
the operator creates and removes its own unique private child directory.

## CI and real-canary gate

CI uses synthetic tarballs and mocks the decryption/verifier process. It must
prove at minimum:

- valid restore shape reaches the verifier and cleans plaintext;
- sidecar mismatch fails before decrypt;
- decrypt failure fails closed and cleans plaintext;
- absolute/traversal paths and escaping symlink/hardlink targets are rejected;
- an archive-validation failure removes plaintext;
- a production work target is refused;
- exact-source verification rejects a dirty verifier/operator file;
- verifier failure propagates non-zero;
- cleanup failure is visible and forces FAIL;
- evidence excludes fixture-private values and sensitive paths.

CI does **not** decrypt a real backup and does not prove recovery. After merge,
one separately approved real retained-backup canary must use the exact reviewed
SHAs and explicit current production application root, leave production service
and DB state unchanged, record RPO/RTO evidence, and prove cleanup. Only that
canary can satisfy the remaining host evidence for `hermes-tech#90`.

`RPI5_MAIN_CHANGE_REQUIRED=yes`

`HERMES_TECH_DEPLOY_REQUIRED=no`
