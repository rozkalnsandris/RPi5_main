# Cloudflare P0 read-only reconciliation operator — issue #179

Status: **source contract / GET-only / no production mutation**

Canonical design:
- `docs/CLOUDFLARE_ZERO_TRUST_MOBILE_AUDIT_2026-08-17.md`
- `docs/CLOUDFLARE_OWNER_PHONE_ACCESS_CONTRACT.md`
- `ops/contracts/cloudflare-hostname-policy.yaml`

## Purpose

This operator performs the first fresh Cloudflare control-plane reconciliation after the
2026-08-17 cross-project audit. It compares current Access and Tunnel state with the
public-safe hostname registry without changing Cloudflare, DNS, the RPi5 host, or any
application.

It is deliberately expected to return `BLOCKED` while known policy drift remains.
`BLOCKED` means the read-only audit found a condition that must be reconciled before a
write gate. It does **not** mean the operator attempted or partially performed a change.

## Cloudflare API surface

The Python core exposes only HTTP `GET`. It has no generic HTTP method argument and no
write helper.

The allowed Cloudflare reads are:

1. `GET /user/tokens/verify`
2. `GET /accounts/{account_id}/access/organizations`
3. `GET /accounts/{account_id}/access/apps`
4. `GET /accounts/{account_id}/access/apps/{app_id}/policies`
5. `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}`
6. `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`

Pagination is supported for Access application and application-policy lists.

The source was designed against the current Cloudflare API reference reviewed on
2026-08-17. A later execution must still fail closed if Cloudflare changes a response
shape.

## Secret and privacy boundary

The operator requires these bindings outside Git:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_TUNNEL_ID`
- `CLOUDFLARE_API_TOKEN`

The wrapper prompts for the API token on `/dev/tty` with terminal echo disabled if the
token is not already present in the environment.

The public-safe JSON output intentionally never includes:

- API token or token ID;
- account ID or tunnel ID;
- owner/family email values;
- home/source IP selector values;
- Access application IDs or policy IDs;
- Access AUD values;
- Cloudflare team/auth-domain value;
- exact Tunnel origin URL, private IP, or origin port.

Raw selector values are inspected only in process memory. Output contains selector
**types and counts** only.

## Registry reconciliation

Each hostname is classified as `PUBLIC`, `FAMILY_PRIVATE`, or `ADMIN`.

`audit_route_presence` records the expected current routing state for this audit:

- `present`: an exact Tunnel ingress route must exist;
- `absent`: the route is deliberately not live yet;
- `not-applicable`: delivery does not use the shared RPi5 Tunnel.

This field is an audit expectation, not authorization to create or remove a route.

The operator additionally proves:

- no unclassified Tunnel hostname exists;
- no duplicate hostname route exists;
- exactly one final `http_status:404` catch-all exists;
- loopback-only desired routes actually classify as loopback;
- explicit LAN break-glass routes remain private-LAN origins;
- ADMIN/FAMILY Access applications do not rely on `BYPASS`;
- PUBLIC hostnames do not unexpectedly resolve to Access applications;
- exact-owner targets resolve to an exact application rather than a broad wildcard;
- `Allow Everyone` and broad `login_method` selectors fail closed;
- exact-owner applications have exactly one explicit email include selector;
- `Protect with Access` is proven from effective Tunnel `originRequest.access` state:
  `required=true`, at least one AUD tag, team name present, and team name matching the
  current Zero Trust organization.

Cloudflare documents that a more-specific Access application/path takes precedence over
a broader parent path. The resolver therefore chooses the single most-specific matching
root-host application and fails closed if equally specific applications are ambiguous.

## Local execution after merge

Do not execute this operator from an unreviewed branch. Required sequence:

1. source PR merged;
2. exact-main CI is green;
3. fresh clone or clean exact-main checkout on the trusted Lenovo workstation;
4. set the account/tunnel bindings outside Git;
5. run the wrapper and enter the token only at the hidden prompt.

Example with placeholders only:

```bash
cd /path/to/RPi5_main
git fetch origin
git switch main
git pull --ff-only

export CLOUDFLARE_ACCOUNT_ID='<private-account-binding>'
export CLOUDFLARE_TUNNEL_ID='<private-tunnel-binding>'

umask 077
bash ops/bin/cloudflare-zero-trust-reconcile \
  > /tmp/rpi5-cloudflare-p0-179.json
rc=$?

unset CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_TUNNEL_ID CLOUDFLARE_API_TOKEN
printf 'P0_RC=%s\n' "$rc"
python3 -m json.tool /tmp/rpi5-cloudflare-p0-179.json
```

Exit codes:

- `0`: reconciliation PASS, no blockers found;
- `2`: preflight/API/shape/credential binding failure;
- `3`: GET-only reconciliation completed and found one or more blockers/drift gates.

Because the currently known broad wildcard/BYPASS mismatch has not yet been changed,
exit code `3` is a legitimate expected first production result.

## Required evidence after the first live GET-only run

Only the already-sanitized JSON may be summarized into GitHub issue #179.

Before posting, independently grep the saved output to confirm it does not contain the
private account/tunnel IDs, owner email, home public IP, token fragment, Access AUD
values, or auth-domain value.

The first live evidence should record:

- exact `RPi5_main/main` SHA;
- exact-main CI run;
- operator exit code;
- result `PASS` or `BLOCKED`;
- hostname count;
- sanitized blockers/drift list;
- application domain/policy-shape summary;
- Tunnel status/connection count;
- sanitized route origin classes and Protect-with-Access proof.

## Owner-phone preflight

This source phase does **not** enroll or modify the phone.

Before a later write gate, confirm on the Samsung/Android device:

- current Cloudflare One Agent is installable and supported;
- the intended Zero Trust organization can be selected;
- the owner identity binding is known privately;
- Android screen lock/biometrics are enabled;
- the planned posture condition is `Require WARP`;
- both home Wi-Fi and 4G/5G can be tested independently;
- the fallback remains normal Access/global SSO sessions if
  `Authenticate with Cloudflare One Client` Beta is not selected;
- a lost-phone procedure can revoke the device/user session without relying on the
  phone itself.

MAC address binding is explicitly outside the target design.

## Mutation boundary

This operator does not authorize or perform:

- Access application/policy creation, update, deletion, or reordering;
- device enrollment or posture-policy changes;
- Tunnel route/configuration writes;
- DNS changes;
- Bypass removal;
- Cloudflare session-setting changes;
- RPi5 host/firewall/systemd/Docker mutation;
- application deploy or restart.

The next Cloudflare write plan may be prepared only from fresh read-only evidence and
still requires a separate explicit owner authorization.
