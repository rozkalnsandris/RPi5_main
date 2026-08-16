# Home Assistant trusted-proxy production gate

Issue: #171

## Purpose

This document defines the host-owned production gate for one narrowly scoped Home Assistant hardening change: replace broad private-network entries in `trusted_proxies` with the single immediate proxy source already proven by the application repository's live verifier.

This is an **operator contract**, not production authorization. Merging this document does not authorize a Home Assistant configuration write, backup creation, reload/restart, Cloudflare change, Docker change, firewall change, or systemd change.

## Ownership boundary

- `rozkalnsandris/home-assistant-config` owns the reviewed declarative Home Assistant source, privacy rules, exact-version validation, and the trusted-proxy candidate proof.
- `rozkalnsandris/RPi5_main` owns host/runtime/ingress/backup/apply and rollback machinery.
- Private addresses, exact live filesystem paths, secrets, raw Home Assistant configuration, backup archives, and credentials remain outside Git and public evidence.

## Proven upstream state

The application repository has already established all of the following before this host gate:

- Home Assistant version `2026.8.2`;
- a live cloudflared-owned origin connection to Home Assistant port `8123` while real authorized ADMIN traffic was flowing;
- the immediate source class is the RPi5 primary private IPv4;
- the minimum candidate scope is exactly one host address;
- the exact address is never emitted or committed;
- the candidate passed Home Assistant `check_config --fail-on-warnings` using the already-running Home Assistant image;
- production `/config` was not mounted or modified by candidate validation;
- application-config exact `main` at the handoff point is `d12b486a09dcffdf128d3923a7cc24b12380d474`.

A future production operation must re-bind to the then-current exact application revision and must not assume this handoff SHA remains current forever.

## Official behavior relied on by this gate

Home Assistant documents that `use_x_forwarded_for` requires carefully scoped `trusted_proxies`, and that an immediate reverse proxy not present in that list can cause requests carrying forwarded headers to be rejected. Home Assistant also provides configuration checking before restart/reload.

Home Assistant backups are a separate recovery layer from Git. Current Home Assistant backup support applies across installation types; the production gate requires a fresh backup that includes the configuration data relevant to this change, plus an off-device copy and available recovery material.

Cloudflare Access remains unchanged by this operation. Home Assistant is an ADMIN application and the authorized external path must continue to pass the existing Access policy after the Home Assistant change.

## Phase A — immutable source binding

Immediately before any production preparation:

1. Record the exact `RPi5_main` `main` SHA.
2. Record the exact `home-assistant-config` `main` SHA.
3. Confirm both repositories are clean/current for the intended operation.
4. Re-run the trusted-proxy candidate validator from the exact intended application SHA.
5. Require sanitized decision `VALIDATED_FOR_PREPRODUCTION` and exact running Home Assistant version match.
6. Stop fail-closed on any mismatch, warning, version drift, or changed candidate scope.

The exact private address remains local and must not be copied into an issue, PR, log, command transcript, or evidence artifact.

## Phase B — access proof before mutation

Two independent access paths must be live immediately before the change:

### Remote ADMIN path

- Use the normal Home Assistant public hostname through Cloudflare Access.
- Authenticate with the existing ADMIN policy.
- Confirm the Home Assistant dashboard fully loads.
- Keep this browser session available for post-change verification.

### LAN break-glass path

- From a second LAN client, connect directly to the Home Assistant LAN listener rather than through the public hostname.
- Confirm the Home Assistant frontend responds and the normal authenticated dashboard can be reached.
- Keep this LAN path available until post-change verification is complete.

The RPi5 checking its own listener is not sufficient evidence for LAN break-glass. The second-client proof is required because it validates the actual recovery path an operator would use if the external reverse-proxy path fails.

## Phase C — backup and primary rollback material

Backup preparation is itself a host/runtime write and therefore requires explicit owner authorization before it is created.

After authorization and before the Home Assistant config mutation:

1. Create a fresh Home Assistant manual backup using the supported Home Assistant backup workflow.
2. Confirm the backup includes the configuration data needed to recover this change.
3. Download or copy one backup off the RPi5.
4. Ensure the backup emergency/recovery material needed for restore is available off-device.
5. Retain the exact pre-change private HTTP configuration bytes in a private host-only rollback location.
6. Record only sanitized metadata publicly: backup-created yes/no, off-device-copy yes/no, recovery-material yes/no, and pre-change-file-retained yes/no.

Never commit or print the backup archive, backup key, exact private path, exact private IP, or raw pre-change configuration.

For this one-file change, the retained pre-change file is the **primary fast rollback**. The Home Assistant backup is the broader recovery layer if a simple file rollback is insufficient.

## Phase D — bounded candidate assembly

The production candidate must be limited to the private HTTP binding already owned outside Git.

Required semantics:

```yaml
use_x_forwarded_for: true
trusted_proxies:
  - <the one exact immediate proxy source proven by the live verifier>
```

The production diff must show only the intended narrowing of `trusted_proxies`. Do not change the Cloudflare hostname, Access policy, tunnel route, listener/bind, Docker network mode, firewall, unrelated Home Assistant HTTP options, automations, dashboards, integrations, secrets, or `.storage`.

Before mutation:

- validate the full candidate against the exact running Home Assistant version;
- verify the diff is bounded to the reviewed private HTTP binding;
- verify ownership and mode preservation for the target file;
- stop if the live file has changed since rollback bytes were captured.

## Phase E — explicit production authorization

A production write and Home Assistant restart are separate from source merge approval.

The operator must state an explicit authorization identifying this exact operation before either action occurs. The authorization must cover:

- the one bounded private HTTP configuration write;
- the Home Assistant restart required to ensure the HTTP integration is reloaded;
- the immediate post-change remote and LAN verification;
- rollback using the retained pre-change bytes if verification fails.

No Cloudflare, Docker, firewall, systemd, device, automation, or unrelated Home Assistant change is implied by that authorization.

## Phase F — guarded apply

Only after Phase E authorization:

1. Re-check exact source bindings and live-file freshness.
2. Apply only the reviewed private HTTP binding change while preserving file owner/mode.
3. Run Home Assistant configuration validation against the full live candidate.
4. If validation fails, restore the retained pre-change bytes immediately and do **not** restart into the invalid candidate.
5. If validation passes, restart Home Assistant to activate the HTTP configuration.
6. Do not modify shared `cloudflared.service`, Cloudflare Access, tunnel routes, Docker networking, or firewall as part of this operation.

## Phase G — post-change verification

Verification order after Home Assistant returns:

1. Confirm Home Assistant process/container is running on the expected version.
2. Verify LAN break-glass from the second LAN client.
3. Verify the authorized remote ADMIN path through Cloudflare Access.
4. Confirm the Home Assistant dashboard fully loads through both paths.
5. Re-run the sanitized trusted-proxy topology verifier while authorized remote traffic is flowing and require the same one-host scope.
6. Check for configuration/startup errors without publishing private coordinates or secret-bearing log lines.

Do not declare success if either LAN or remote access fails.

## Phase H — rollback

Rollback is mandatory on failed post-verification or unexpected runtime behavior.

Primary rollback:

1. Restore the exact retained pre-change private HTTP configuration bytes.
2. Validate the restored configuration.
3. Restart Home Assistant if the changed configuration had already been activated.
4. Verify LAN break-glass first, then the remote Cloudflare Access path.

Escalated recovery:

- use the fresh Home Assistant backup only if the exact-file rollback is insufficient or broader state must be restored;
- keep the backup and pre-change bytes until the post-change stability gate is explicitly complete.

A rollback must never restore `.storage`, recorder data, credentials, or unrelated runtime state from Git.

## Public evidence allowed

Allowed public evidence is limited to booleans, version/SHA bindings, safe classifications, and PASS/FAIL decisions. Examples:

- exact repository SHAs;
- Home Assistant version;
- `candidate_validated=true`;
- `remote_access_before=true`;
- `lan_break_glass_before=true`;
- `backup_created=true`;
- `backup_off_device=true`;
- `prechange_file_retained=true`;
- `full_check_config_passed=true`;
- `restart_authorized=true`;
- `lan_break_glass_after=true`;
- `remote_access_after=true`;
- `rollback_required=false`.

Never publish exact private addresses, private filesystem paths, raw configuration, raw backup metadata that contains sensitive names, tokens/cookies, Access credentials, or raw log lines.

## Stop conditions

Stop without production mutation if any of these are true:

- exact repository binding changed unexpectedly;
- Home Assistant version no longer matches the validated target;
- candidate validation is not `VALIDATED_FOR_PREPRODUCTION`;
- remote ADMIN access is not working before mutation;
- second-client LAN break-glass is not working before mutation;
- fresh backup/off-device recovery material is not ready after authorized backup preparation;
- live private HTTP file changed after rollback capture;
- diff contains anything beyond the reviewed HTTP trust narrowing;
- full configuration validation fails;
- production write/restart authorization is absent or ambiguous.

## Current boundary

This document prepares the gate only.

**Production deploy/change: NO.**
