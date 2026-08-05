# V09 backup ownership findings

## Result

The host-wide encrypted backup implementation has been imported into the infrastructure repository without changing its bytes.

The four imported files match Hermes Tech snapshot `194083f0d850c888d23f751aeb51e69a561a047a` by both Git blob identity and SHA256.

## Clean-run evidence

GitHub Actions Validate run `31006721429`, job `92308347609`, passed on the first import commit.

The clean runner produced:

```text
5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735  ops/bin/rpi5-backup
65e4d465fc13c05c4a19842a4c6a5f4c3410bd5ac0ede1bffe79c54d359b2a8c  ops/backup/rpi5-backup.conf.example
d9ef8658cb78ea85a3c7bb8e3853b03eab4c896399e58c35ef5b960df2a51697  ops/cron.d/rpi5-backup
08e0b02be895592ffd1fd56ed6c5849cdc0e7b117c161e9382165ebcf05765e2  ops/logrotate.d/rpi5-backup
```

The same run passed the existing inventory, access-model, runtime-baseline, runtime-diff, review, lineage, memory-pressure, Python compilation, and secret-guard checks.

## Preserved contracts

The import preserves the V12 script, nightly `02:00` schedule, seven-day local retention, thirty-day remote retention, age encryption, local decrypt/tar verification, SQLite snapshot integrity check, rclone upload, remote-size verification, and fourteen-rotation logrotate policy.

## Not verified or changed

No RPi5 host access occurred. The following remain intentionally unverified until a separate approved evidence step:

- installed-file SHA256, mode, owner, and group;
- current cron daemon state;
- current logrotate parse;
- latest production backup health;
- equality of the installed configuration to the tracked example.

No backup ran. No archive was read, created, uploaded, deleted, restored, or inspected. No service, cron, logrotate, configuration, secret, key, credential, database, or runtime file changed.

## Ownership transition state

After this PR is squash-merged, `RPi5_main` becomes the source of truth for the four host-wide files.

Hermes Tech issue #9 remains open until a separate Hermes Tech PR removes its duplicated copies and points to the exact merged infrastructure commit. Production verification and any future deployment remain separate explicit approvals.
