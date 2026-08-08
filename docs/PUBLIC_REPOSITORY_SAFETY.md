# Public repository safety boundary

`RPi5_main` is intentionally public. Public visibility is not an authorization boundary for the Raspberry Pi, Cloudflare account, home network, or application data.

## Public by design

The repository may contain architecture, service roles, public hostnames, source-controlled systemd/Docker contracts, tests, non-secret checksums of repository artifacts, and sanitized production PASS/FAIL evidence.

## Keep private by default

Do not add real credentials, `.env` contents, authorization headers, personal email/phone details, private LAN coordinates, user-specific home paths, transient Docker bridge coordinates, process/container identifiers, boot IDs, or credential-file locations to documentation, issues, PR bodies, comments, screenshots, or new general-purpose source files.

Use role-oriented placeholders such as `$LAN_IP`, `$LAN_CIDR`, `$TECH_PUBLIC_DIR`, `$ORIGIN_PORT`, `$CONTAINER_ID`, and `$CREDENTIAL_PATH` in public documentation.

## Existing operational literals

A small amount of legacy source still contains exact host-private literals because the files are executable production contracts rather than descriptive documentation. Those values are not credentials, but they increase reconnaissance value. They are intentionally not rewritten opportunistically in this public-hardening change because changing an authoritative unit/operator can create a production deploy or recovery dependency.

The migration rule is:

1. do not spread an existing private literal into another file;
2. when an authoritative runtime file next needs modification, prefer a reviewed configuration boundary or neutral variable instead of copying the literal;
3. remove obsolete literal-bearing documentation when it can be sanitized without changing runtime behavior;
4. treat a real credential differently: rotate/revoke first, then remediate reachable history and surfaces.

## CI enforcement

`make validate` runs two local, network-free guards:

- `scripts/check-no-secrets.sh` blocks secret-like tracked files and selected credential patterns while printing only affected file paths, never matching values;
- `scripts/check-public-safety.sh` checks newly added diff lines and blocks known host-private literals plus non-example email addresses without printing the matched value.

GitHub Actions additionally runs `scripts/run-gitleaks-ci.sh` on a GitHub-hosted runner. The scanner:

- downloads exactly Gitleaks `8.18.4` and verifies the release archive against the release checksum manifest;
- runs a synthetic rule-matching canary before trusting a clean scan;
- requires redaction of the canary value;
- independently verifies the complete reachable history stream and then scans all reachable Git history;
- stores no findings artifact and posts no automated PR comment.

The version is intentionally a conservative known-good control rather than `latest`: the upstream report for the Gitleaks `8.30.1` detection regression explicitly shows the same canonical GitHub PAT shape being detected by `8.18.4`. The first attempted `8.30.0` pin in PR validation did not pass this repository's runtime canary, so it was rejected rather than trusted. Any future scanner upgrade must pass the same canary before the history result is accepted.

## GitHub Actions policy

- GitHub-hosted runners only for public PR validation;
- repository permissions remain `contents: read` unless a separate job proves a need for more;
- checkout credentials are not persisted;
- third-party Actions are pinned to full commit SHAs;
- full Git history is fetched only for read-only validation/scanning;
- no repository/environment credential is required by ordinary fork PR validation;
- never use `pull_request_target` to execute untrusted PR code.

## Evidence policy

Security findings should identify the category and affected path only. Do not paste the matched token, password, private key, private origin, personal address, or credential path into public evidence in order to prove that a guard worked.

## Production impact

This policy and its CI gates do not mutate the RPi5 or any application runtime.

`Production deploy/change REQUIRED: NO`
