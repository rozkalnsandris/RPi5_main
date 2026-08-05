# Runtime baseline archive

This directory is managed only by the V04 controlled review workflow.

A future accepted promotion archives the previous canonical baseline, its
deterministic Markdown projection, the verified V03 diff, the human decision,
and a checksummed transition record. Direct restoration is not implemented;
repository rollback uses `git revert`, and any future rollback workflow requires
a separately reviewed chronology exception.
