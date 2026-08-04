# Disaster recovery

V01 does not modify the Raspberry Pi and therefore has no production rollback action. Repository rollback is a reviewed revert of the relevant commit.

Before a future production apply, the task must identify an exact commit, capture an approved backup, define verification, and document a tested rollback path. Backups and runtime data must remain outside Git.
