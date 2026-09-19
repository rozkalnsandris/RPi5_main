# Weather v9 capability-state bootstrap fixture

Issue #623 recovery tests use isolated temporary directories and synthetic regular files only. They must never read or mutate live `/etc`, `/var/lib`, systemd, Docker, networking, credentials, or manager checkout state.

The fixture contract represents exactly one accepted runtime baseline: reviewed capability artifacts present and both durable state objects absent. Mixed, already-complete, staging-residue, symlink, ownership/mode/hash, and provenance drift cases are rejection fixtures.
