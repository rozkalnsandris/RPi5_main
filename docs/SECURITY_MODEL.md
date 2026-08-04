# Security model

The repository is private, but privacy is not a substitute for secret handling. Credentials, private keys, cookies, tokens, passwords, database data, backups, and runtime data are excluded from Git.

The V01 collector uses an explicit command allowlist, bounded output, sanitization, private result permissions, and a verifier. It never reads process or container environments, raw configuration, database data, backups, or key material.

GitHub Actions has read-only repository permissions, uses GitHub-hosted runners, requires no repository secrets, and only runs validation.
