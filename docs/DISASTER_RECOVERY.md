# Disaster recovery

V01 does not modify the Raspberry Pi and therefore has no production rollback action. Repository rollback is a reviewed revert of the relevant commit.

Before a future production apply, the task must identify an exact commit, capture an approved backup, define verification, and document a tested rollback path. Backups and runtime data must remain outside Git.

## V09 encrypted backup ownership

The V09 repository import does not modify the installed backup and therefore has no host rollback action. Repository rollback is a reviewed revert of the V09 ownership commit.

The tracked backup source, provenance, installed mapping, no-op verification gate, future deployment controls, and rollback procedure are defined in `V09_BACKUP_OWNERSHIP_CONTRACT.md`.

A future approved host deployment must privately preserve the current installed script, configuration, cron entry, and logrotate entry before replacement. Rollback restores those exact pre-change files with their recorded owner and mode, then repeats checksum, script syntax, cron, and debug-only logrotate verification. Backup archives, keys, credentials, and runtime data remain outside Git and must not be copied into repository evidence.
