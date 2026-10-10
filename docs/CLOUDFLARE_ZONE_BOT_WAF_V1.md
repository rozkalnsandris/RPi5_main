# `rozkalns.net` named AI crawler WAF — source-only v1

## Decision and boundary

Owner requested bot protection for the **entire `rozkalns.net` zone**, including the public CV apex and `coloring.rozkalns.net`, while preserving ordinary human access and search engine indexing. This is a source-only rule/operator/test proposal. **No Cloudflare change, deployment, token provisioning, root install, or merge is included.** This source proposal does not claim to protect private data: use Cloudflare Access, application authentication, API authorization, and server-side access control on sensitive services.

Cloudflare `Wrangler` handles Workers; the correct API for WAF rules is the **Rulesets API**. The only source-level action proposed is one `block` custom WAF rule in the existing/new **zone** `http_request_firewall_custom` phase entrypoint. The host expression covers precisely `rozkalns.net` and `.rozkalns.net` subdomains. It does not touch DNS, tunnels, Access, existing rules or workers. All paths (including public CV and Coloring Pages media) are included **only when the named bot User-Agent matches**.

`cf.bot_management.score` is Enterprise-only; this proposal uses Free-plan-compatible `http.user_agent`, `lower()`, `ends_with()` with an enumerated set of known AI crawlers/agents. Googlebot/Bingbot and search-purpose bots such as OAI-SearchBot, Claude-SearchBot, and PerplexityBot are not targeted. No blanket managed challenge, zone-wide Bot Fight Mode, search-engine `skip`, IP-based bypass, rate-limit slot consumption or rewriting of existing WAF rules. This preserves existing M2M/Webhook traffic unless its User-Agent happens to match one of the forbidden agents; that edge case must be checked before any LIVE activation.

## Limits and why it is not a privacy boundary

**User-Agent is client-controlled and spoofable.** A scraper can impersonate Chrome, and a human can save any publicly downloadable PNG or CV. This source rule does not identify all malicious bots, provide rate limiting or prevent mass fetching with forged User-Agents. Prefer Cloudflare managed AI bot policies (`Training=Block`, `Agent=Block`, `Search=Allow`) where supported, as a separately owner-gated product-setting action. The managed setting is not the WAF Rulesets API and cannot be pretended to be activated by this PR. For public PNG anti-harvesting, separately review per-path rate limiting based on observed traffic, plan limits and verified SEO/printing behavior. Private content should not be public in the first place.

Historical `RPi5_main#206` records an actual GitHub-runner outage caused by Cloudflare Free zone-wide Bot Fight Mode on `control.rozkalns.net`, and the owner's decision to retire that global heuristic. We do **not** turn it back on, or apply a blanket challenge that would break Cloudflare Access service tokens, webhooks, Home Assistant clients, or other machine integrations. The existing `ops/contracts/cloudflare-hostname-policy.yaml` controls PUBLIC/ADMIN/FAMILY_PRIVATE trust classes, unchanged by this work.

## Source operator

- Script: `scripts/cloudflare_zone_bot_waf.py`.
- Offline preview (no network/secret): `python3 scripts/cloudflare_zone_bot_waf.py --plan`.
- Proposed future installed path: `/usr/local/sbin/rpi5-cloudflare-zone-bot-waf`, `root:root 0500`.
- Proposed future exact-release metadata: `/usr/local/libexec/rpi5-cloudflare-zone-bot-waf/release.json`, `root:root 0400`, fields `source_sha` and `operator_sha256`.
- **Separate dedicated** root-owned `0600` credential source: `/etc/rpi5-secrets/cloudflare/zone-waf-writer.json`, containing only `zone_id`, `zone_name=rozkalns.net`, and `api_token`. Credential requires zone-scoped **Zone Read + Zone WAF Edit** because `GET /zones/{zone_id}` checks the exact zone and the Rulesets API needs WAF edit permission. Never reuse Access/Tunnel credentials. No secret value is committed, displayed or read in this source-only work.
- Future read-only preflight (requires installed exact-release, root and dedicated credential): `rpi5-cloudflare-zone-bot-waf --preflight --expected-main <exact-40-char-sha>`.
- Future **separately** authorized, root-installed one-time apply: `rpi5-cloudflare-zone-bot-waf --apply --expected-main <exact-40-char-sha> --confirm CREATE-ROZKALNS-BOT-WAF-RULE`.

## Reviewed source-only installer and local provisioning preparation (#962)

The unprivileged installer `scripts/install-cloudflare-zone-bot-waf.py` has no auto-install behavior. It requires the current exact `main` SHA, a clean `main` checkout, canonical GitHub origin, tracked operator source, non-root caller, non-interactive sudo availability, fixed root-owned non-group/world-writable parent directories, and absent fixed destinations (including dangling symlinks). It reads and pins the exact operator bytes and SHA-256 release metadata **before** the first mutation. The previous installer used `sudo python3 -c ROOT_INSTALL_WRITER`, which was blocked by the platform's safety review. The reason for that safety decision is not available; this change does not claim to resolve or bypass that independent policy.

The redesigned installer uses only three fixed `sudo -n` GNU coreutils commands (no privileged Python, shell interpreter, dynamic `-c` code, or sudoers edit): `/usr/bin/mkdir -m 0700 -- <fixed-release-dir>` for an initially absent directory; then `/usr/bin/install -T -o root -g root -m 0500 -- /dev/stdin <fixed-operator>` to copy the **captured source bytes**; and finally the same `install -T` with mode `0400` to copy the exact-release metadata bytes to `release.json`. `-T` disallows interpreting a destination as a directory; the initial absent-path and root-owned-parent checks limit overwrite/race risk. Since generic GNU `install` can replace existing files, this remains dependent on the fixed root-owned non-writable parent trust boundary. Do **not** treat this as an atomic three-file transaction, and do **not** grant generic sudo rights to arbitrary arguments. Post-install read-only `stat` and `sha256sum` verify every target's owner, mode and SHA-256. The code neither provisions credentials nor makes Cloudflare requests. <https://www.gnu.org/software/coreutils/manual/html_node/install-invocation.html>

Read-only install preflight (on the approved RPi5 checkout, when separately authorized):

```bash
python3 scripts/install-cloudflare-zone-bot-waf.py --expected-main <exact-40-char-current-main>
```

The **future separately owner-gated** one-time installation adds `--apply --confirm INSTALL-ROZKALNS-ZONE-BOT-WAF`. The first privileged `mkdir` dispatch is the first host mutation; each subsequent fixed `install` dispatch is bounded to one named file. A failure or ambiguous result after the first dispatch means **STOP** with potentially partial installed state; there is no retry, cleanup, rollback, overwrite repair or fallback executor. A previous install blocks; upgrading is deliberately unsupported. Source review or CI passing does not grant execution permission or guarantee the platform tool will accept a later, independently authorized LIVE operation.

The installed operator now supports **future separately owner-gated** interactive provisioning:

```bash
sudo -n /usr/local/sbin/rpi5-cloudflare-zone-bot-waf --provision-secret --expected-main <exact-installed-release-sha> --confirm PROVISION-ROZKALNS-ZONE-WAF-SECRET
```

This **must** run from an owner-controlled local/SSH terminal with controlling TTY. It does not accept token or zone ID in arguments, environment, stdin, GitHub, chat or logs. Both values are entered with hidden `getpass` prompts; an echoed fallback is rejected. It requires an already existing root-only dedicated Cloudflare secret directory, checks the installed operator/release and secret absence before prompting, validates the actual `rozkalns.net` zone with `GET /zones/{id}`, and accepts only exact-zone credentials. It uses `O_EXCL|O_NOFOLLOW` to create the sole 0600 credential file without replacing anything. A successful read does *not* prove Zone WAF Write capability; the owner must verify token rights separately, and no write is attempted during provisioning.

All commands above document capabilities for future decisions; no LIVE action, credential provisioning, permission change, installation or WAF API mutation is authorized by merging source. `--plan` remains available without a secret or network. The operator refuses privileged operations from the repository checkout.

## Installed operator size-limit regression and replacement design (#967)

The first owner-entered `--provision-secret` command on the already installed release `861c1da26caba215ef05a1681a6bcd190641c43f` stopped at `protected_file_too_large` **before any Zone ID or token prompt**. The 14,162-byte root-owned operator could not pass its own `owned_file()` integrity read because a shared 8,192-byte cap had also been applied to executable source. Read-only host evidence showed the dedicated credential target absent, and no WAF change occurred.

**Source fix:** retain a strict 8,192-byte read bound for `release.json` (0400) and the dedicated credential (0600). Permit at most 131,072 bytes **only** when reading the exact installed `/usr/local/sbin/rpi5-cloudflare-zone-bot-waf` path with required 0500 mode; keep root ownership, regular-file/no-symlink and descriptor metadata checks and verify the SHA-256 against release metadata. The larger bound matches the source installer's existing 128 KiB maximum. A source merge does not modify the installed root-owned executable.

**Future safe replacement design — NOT implemented or authorized by this source-only PR:**

1. Obtain a **new, explicit owner LIVE authorization** naming the exact new merged `RPi5_main/main` SHA, actual incumbent operator SHA-256 and release metadata identity, fixed host/path, temporary staging targets, and permitted single-use root replacement operations. Confirm clean exact-source RPi5 checkout via a **separate owner-authorized source sync** if required. The current first-install-only script explicitly rejects existing targets; do **not** rerun it, delete the existing operator, or silently overwrite through an alternate installer.
2. Read only the **incumbent file metadata, SHA-256 and release identity** without displaying or opening credentials. Require root:root, modes 0500/0400, expected file types, no symlinks, root-controlled non-group/world-writable ancestor directories, and an unchanged incumbent release. Pin the candidate source bytes (no more than 128 KiB), candidate SHA-256, expected exact-source release metadata bytes and their digest **before** the first mutation. Validate that both candidate paths and staging destinations have matching underlying filesystems, and that all dedicated fixed staging names are absent.
3. A future reviewed replacement executor must stage the captured operator bytes into one fixed absent root-owned 0500 temporary file in `/usr/local/sbin` and its captured release bytes into one fixed absent root-owned 0400 temporary file in `/usr/local/libexec/rpi5-cloudflare-zone-bot-waf`. Verify their metadata and SHA-256 before cutover. No caller-selected paths, environment or shell commands, sudoers modifications, untrusted privileged Python evaluator or root execution of Git checkout content. Do not touch the dedicated credential path.
4. Require exclusive maintenance/no concurrent operator invocation during cutover. The future executor may perform only **one individually atomic same-directory replacement of each fixed target** after rechecking incumbent/staged identities. Publishing the executable and release JSON is **not** a single atomic transaction: the intermediate state may contain mismatched versions. Fail closed on any ambiguous or failed stage/write/rename/verification, preserve evidence, and **STOP** with no retry, automatic cleanup, rollback or alternate mutation until a fresh exact owner decision. No WAF/API changes are part of replacement.
5. After the two intended replacements, independently verify exact installed operator bytes/digest, root:root ownership and 0500 mode, release root:root 0400 mode, `source_sha` equal to the newly authorized main SHA, and metadata's operator SHA-256 equal to the actual installed file. Only then can separately authorized owner-local-TTY provisioning be reconsidered; it remains a different risk/authorization gate. Even if source PR and CI pass, the current root operator remains **broken** until that separate replacement is implemented, reviewed and executed.

Do **not** increase the credential/release size cap as a workaround, perform a manual `sudo cp`/overwrite, remove the current install, or rerun the failed provisioning command. The manual replacement description is a design, **not** an instruction or authorization to perform LIVE steps.

## Fail-closed Cloudflare preflight and one-write boundary

1. Verify installed exact source identity/hash and dedicated root-only secret file metadata (no symlink); check actual `GET /zones/{zone_id}` returns the expected zone name.
2. `GET /zones/{zone_id}/rulesets/phases/http_request_firewall_custom/entrypoint`: only `200` (validate kind/phase/rules) or `404` (absent entrypoint) is an allowed branch. Reject existing matching `ref`/expression or invalid metadata. Preserve existing rule count and order.
3. If entrypoint exists, exactly one `POST /zones/{zone_id}/rulesets/{entrypoint_id}/rules`; if absent, exactly one `POST /zones/{zone_id}/rulesets` creates a zone-phase entrypoint with the single target rule. **No PUT, PATCH, DELETE, retry or fallback.** If no Free custom rule capacity, reject the provider error; do not replace an unrelated rule.
4. `GET` the entrypoint after the POST. Verify exactly one new target rule (`ref`, expression, block/enabled) was added and all prior rules are semantically unchanged and in order. Any drift or API ambiguity after mutation => STOP, minimum sanitized evidence only, new owner decision.
5. Prior to owner authorization for LIVE: verify real existing rule inventory/quota (Cloudflare Free offers 5 zone custom rules), provider expression acceptance, other services' webhooks/Access flows, and public Googlebot/Bingbot/Coloring Pages/CV behavior. Define separate rollback authority if needed; it is **not** contained in the create authorization.

The operator is no substitute for server-side access control; its goal is only to block *identifiable* non-beneficial crawlers at the edge.

Official documentation:
- https://developers.cloudflare.com/waf/custom-rules/create-api/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/add-rule/
- https://developers.cloudflare.com/ruleset-engine/rules-language/functions/
- https://developers.cloudflare.com/bots/additional-configurations/block-ai-bots/
- https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/

- https://developers.cloudflare.com/api/resources/zones/methods/get/
- https://developers.cloudflare.com/waf/custom-rules/

Installer redesign official references:
- https://www.gnu.org/software/coreutils/manual/html_node/mkdir-invocation.html
- https://www.gnu.org/software/coreutils/manual/html_node/Target-directory.html
- https://docs.python.org/3/library/subprocess.html#security-considerations
