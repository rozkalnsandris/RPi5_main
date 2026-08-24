# Disaster recovery

V01 does not modify the Raspberry Pi and therefore has no production rollback action. Repository rollback is a reviewed revert of the relevant commit.

Before a future production apply, the task must identify an exact commit, capture an approved backup, define verification, and document a tested rollback path. Backups and runtime data must remain outside Git.

## V10 encrypted backup ownership

The V10 repository import does not modify the installed backup and therefore has no host rollback action. Repository rollback is a reviewed revert of the V10 ownership commit.

The tracked backup source, provenance, installed mapping, no-op verification gate, future deployment controls, and rollback procedure are defined in `V10_BACKUP_OWNERSHIP_CONTRACT.md`.

A future approved host deployment must privately preserve the current installed script, configuration, cron entry, and logrotate entry before replacement. Rollback restores those exact pre-change files with their recorded owner and mode, then repeats checksum, script syntax, cron, and debug-only logrotate verification. Backup archives, keys, credentials, and runtime data remain outside Git and must not be copied into repository evidence.

## Hermes Tech retained-backup restore drill

The manual source-controlled restore-drill operator and its sanitized evidence
contract are defined in `HERMES_TECH_RESTORE_DRILL.md`. Source review/merge does
not authorize execution against a real retained backup. The first real drill
requires a separate host authorization and must restore only into an isolated
temporary root, run the exact reviewed Hermes verifier, prove plaintext cleanup,
and leave production unchanged. Timer/cadence activation is a later independent
gate after the manual operator has passed.
