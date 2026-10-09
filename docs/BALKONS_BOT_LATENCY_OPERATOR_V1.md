# Balcony Telegram latency: guarded initial installation (#925)

**State:** reviewed source only. No production installation, restart, credential operation,
MQTT command, watering or Telegram timing acceptance follows from a PR merge.

Canonical issue: RPi5_main#925. Prerequisites: #918/#919 (HTTP dispatch isolation),
#920/#922 (offline planner), and the existing read-only
ops/bin/balkons-bot-deploy-verifier.

## Exactly scoped outcome

The sole fixed public source artifacts are:

- ops/lib/balkons-bot.py -> /usr/local/lib/rpi5-balkons-bot.py
- ops/systemd/balkons-bot-runtime-override.conf ->
  /etc/systemd/system/balkons-bot.service.d/95-rpi5-source-credentials.conf

The new reviewed entrypoint is ops/bin/balkons-bot-latency-operator, intended to
be installed separately at /usr/local/sbin/rpi5-balkons-bot-latency-operator
(root:root 0755). **Installing the entrypoint requires its own explicit LIVE
authority** and is not performed by the source PR.

The operator never accepts an alternative repository, service, destination,
source file, shell command or external executable path as an argument. Both
forward destinations must be absent, including symlinks. Existing deployments
require a separate update/reconciliation design; no overwrites.

## Authorization — a CLI switch is NOT permission

An RPi5 run requires a fresh, independently authorized owner LIVE decision.
The command-line --apply switch, a copied command, a commit, a PR merge, and an
operator-provided token cannot create that decision.

Before APPLY, the operator performs an independent **read-only public GitHub
GET** for one numerical issue-comment ID. The response must be a fresh
(maximum 15 minutes), authentic GitHub **User** comment from owner user
277435981 **on RPi5_main#925**. The entire comment body must be exactly one
JSON object with all and only the following fields:

    {
      "schema": "rozkalns.balkons-bot-latency-live-approval.v1",
      "issue": 925,
      "target": "balkons-bot.service",
      "repo_sha": "<current reviewed full main SHA>",
      "source_sha256": "<reviewed public bot source sha256>",
      "baseline_live_path_sha256": "<owner-reviewed legacy path hash>",
      "fragment_path_sha256": "<owner-reviewed unit fragment path hash>",
      "service_user_sha256": "<owner-reviewed service-user fingerprint>",
      "k10_sha256": "<owner-reviewed existing no-SIGKILL drop-in digest>",
      "allow": ["install_two_public_files", "daemon_reload_once", "restart_once"],
      "no_rollback": true
    }

This comment is one **additional proof of the separately taken owner decision**,
not self-issued authority. If it is missing, expired, malformed, unrelated to
issue #925, not owner-authored, or impossible to retrieve, APPLY is blocked.
No GitHub API token is used or requested. Redirects are rejected.

The corresponding --owner-comment-id flag is required for APPLY and forbidden
for CHECK. Source-only work does not create the LIVE comment.

## Owner-operated preflight — no production effect

The existing trusted RPi5 checkout must be a clean, main-branch checkout
with HEAD and local origin/main at the full, separately confirmed current GitHub
commit. If origin has moved, STOP; do not repair via checkout/reset/force.

The operator executable must be root-owned mode 0755 and have exactly the
bytes in the reviewed repository source. This is necessary to prevent a
root execution of editable code straight from the non-root checkout.

The operator requires **root** for its bounded metadata checks; it runs the
existing deploy verifier as **andris/non-root** with only fixed arguments.
That verifier must return READY, preserve five encrypted-credential *metadata*
checks and the accepted historic source **hash-only** boundary, confirm
service/lifecycle/K10 metadata, and return no evidence of credential content
being read or hashed. Raw protected service configuration, ciphertext objects,
legacy source bytes and process secrets are never copied to Git, backups,
terminal output or the new recovery marker.

Example *syntax only*, **not an authorization or ready-to-run command**:

    sudo /usr/local/sbin/rpi5-balkons-bot-latency-operator --check \
      --expected-main <40-char-current-main> \
      --expected-baseline-live-path-sha256 <64-hex> \
      --expected-fragment-path-sha256 <64-hex> \
      --expected-service-user-sha256 <64-hex> \
      --expected-k10-sha256 <64-hex>

CHECK is read-only and does not create root evidence, touch the destination
files, restart the service or transmit any MQTT command.

## Root-only recovery proof and transaction boundary

Before the first write:
1. Verify clean exact source/HEAD/tracked blobs; exact origin/main local ref;
   no changed or conflicting fixed source artifacts.
2. Require fixed target directories root-owned and not writable by other users.
   Reject symlinks and existing forward targets.
3. Require the root-owned existing no-SIGKILL K10 drop-in to match the expected
   SHA-256; verify the old live source **hash only**, old service fragment/path,
   service identity and exact baseline lifecycle through the non-root verifier.
4. Require /var/lib to be root-owned and safe, and the fixed new recovery-state
   directory /var/lib/rozkalns-balkons-bot-latency to be absent.
5. Verify fresh owner issue-comment authority bound to all expected digests.
   Repeat the read-only preflight immediately before starting any mutation.

The legacy private source, original service unit and K10 drop-in remain
**in place, unmodified** and are the recovery baseline; no second copy is
made of the sensitive original. Immediately after mutation starts, a new
root:root 0700 recovery directory contains a root:root 0600 **sanitized
provenance record** (not a backup of credential or source content). If
restoration cannot be proven from that preserved original baseline before the
first mutation, **STOP: no APPLY**.

Approved APPLY sequence, exactly once:
1. Create the exclusive root-only sanitized recovery marker.
2. Write each of the two public files with O_EXCL/O_NOFOLLOW, mode root:root
   0644; verify bytes against its accepted source hash.
3. Run one fixed systemctl daemon-reload and one systemctl restart for
   balkons-bot.service. No implicit extra restart.
4. Run the existing non-root verifier in --verify mode; require PASS, source
   and root-owned file provenance, exact runtime argv/service and unchanged
   non-disclosure guarantees.

After **any** first-write error, timeout, service failure, partial file
publication or ambiguous condition: **STOP**. Do not automatically retry,
remove a partial file, restore an earlier service, roll back, reset, reboot
or run another command. Presence of the recovery-state directory blocks
re-entry until a separate owner-approved recovery procedure is executed.

## Separate owner-gated recovery

The recovery plan relies on retained original unit/source/K10 unchanged.
A distinct authorized root recovery transaction may remove **only** the
two newly installed public files, and only after their path, hash, owner,
mode and active-service status are revalidated against the root-only marker.
It may then perform a separately authorized daemon-reload and one restart,
with a new hash-only verification that the old process executes the original
source and the previously reviewed service lifecycle. This recovery is **not**
implemented as an automatically callable operator mode.

If the legacy source hash, unit provenance, service-user identity, encrypted
credential metadata, K10 overlay, marker integrity or exact installed public
file hashes do not match, recovery is **BLOCKED** pending a separate reviewed
plan. Never back up or copy the private legacy source, plaintext or encrypted
credentials or raw protected unit configuration to make recovery convenient.

## Source-only acceptance and post-LIVE timing

Run make validate, including deterministic tests of absent/existing targets,
source drift, owner-comment auth, partial installation, non-root verifier
acceptance, service invocation sequencing, restrictive modes and no cleanup.

Any actual latency improvement requires **later** owner-authorized timing
probes with sanitized end-to-end counters: Telegram inbound queue delay,
HTTP response delay, bot-to-MQTT publication delay, and ESP32 callback/device
response time. Never claim the original latency incident resolved from CI,
a merge, a single service restart or a dry run.
