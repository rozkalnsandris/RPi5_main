# Cloudflare P1D zero device-enrollment application — issue #179

Status: **SOURCE CONTRACT / PLAN ONLY / NO CLOUDFLARE WRITE AUTHORIZED**  
Live finding date: 2026-08-23  
Tracking issue: #179  
Parent decision: `docs/CLOUDFLARE_P1D_OWNER_PHONE_POSTURE_DECISION.md`

## 1. Why this contract exists

The authorized GET-only `p1d-00-fresh-owner-phone-preflight` can observe three
different counts of Access applications whose type is `warp`. They have
different safety meanings and must not share one generic next step:

- **0** — the device-enrollment application is missing;
- **1** — exactly one enrollment application exists and its policy can be
  inspected deterministically;
- **more than 1** — enrollment application ownership is ambiguous and execution
  must STOP.

A zero count is not an API failure. It is a deterministic missing-state that
requires an application-create canary before owner-phone enrollment can begin.
It must not be routed to the existing-policy tightening canary.

The source preflight remains GET-only. This document defines a future write
contract; it does not implement or authorize that write.

## 2. Cloudflare object model

Cloudflare Device Enrollment Permissions are represented by an Access
application of type `warp`. Access applications are created through:

`POST /accounts/{account_id}/access/apps`

An application can carry an application-exclusive inline Access policy. This
allows the missing enrollment application plus its single owner-only policy to
be established as one forward API state change rather than creating a broad or
temporarily unprotected enrollment application first.

Official references:

- https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/deployment/device-enrollment/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/

## 3. Read-only classification

`p1d-00` must emit only the public-safe classification, never application IDs or
the private owner identity.

| `warp` application count | Classification | Next source gate |
| ---: | --- | --- |
| `0` | `missing` | `p1d-01a-create-owner-only-enrollment-application` |
| `1` | `single` | inspect policy; use `p1d-01` only if it is not owner-only |
| `>1` | `ambiguous` | STOP; do not select or mutate any enrollment app |

The `>1` case must remain fail-closed with
`device_enrollment_application_ambiguous`.

## 4. `p1d-01a-create-owner-only-enrollment-application`

This canary is conditional and remains unauthorized until a fresh exact-main
GET-only preflight proves `application_count=0`.

### Preconditions

Before any forward request:

1. current `RPi5_main/main` and exact-main push CI are positively verified;
2. the reviewed source contract is exact and current;
3. a fresh GET-only preflight still proves exactly zero `warp` applications;
4. exact owner identity is supplied privately and is not printed or persisted;
5. the Cloudflare write credential is separately authorized and limited to the
   required account and Access Apps/Policies write surface;
6. no phone enrollment, posture, device-profile, Gateway firewall, Access
   session or unrelated application change is bundled into this authorization.

### One forward request

Exactly one forward request is allowed:

`POST /accounts/{account_id}/access/apps`

Semantic payload:

```json
{
  "type": "warp",
  "name": "RPi5 Owner Device Enrollment",
  "policies": [
    {
      "name": "RPi5 Owner Device Enrollment",
      "decision": "allow",
      "precedence": 1,
      "include": [
        {
          "email": {
            "email": "exact-owner-identity-private-input"
          }
        }
      ],
      "require": [],
      "exclude": []
    }
  ]
}
```

The placeholder is never replaced in Git. The real identity is private runtime
input.

The first POST attempt consumes its future owner authorization regardless of
HTTP result.

### Deliberately omitted fields

The initial create must not guess or bundle:

- `allowed_idps`;
- `auto_redirect_to_identity`;
- `session_duration`.

Those settings require separate evidence and, if needed, a separately reviewed
change. The create canary establishes only the narrow owner identity enrollment
gate.

### Allowed diff

Only these semantic changes are allowed:

- exactly one new Access application of type `warp`;
- exactly one application-exclusive `allow` policy at precedence `1`;
- exactly one Include selector containing the private exact owner email;
- empty Require and Exclude sets.

No broad email domain, Everyone, IP, service-token or posture selector may be
introduced.

### Forbidden diff

The canary must not change:

- any unrelated Access application or policy;
- reusable device posture rules;
- device profiles;
- Gateway firewall policy;
- client-session or Access-session settings;
- Tunnel, DNS or Worker state;
- any phone/device registration;
- RPi5 host/runtime state.

## 5. Fresh post-write proof

After a successful attributable POST, fresh GET reconciliation must prove:

- exactly one `warp` application now exists;
- it has exactly one owner-only Allow policy;
- Require and Exclude are empty;
- no unrelated Access/device state changed.

Only then may `p1d-01a` be accepted. Phone enrollment remains a later,
separately authorized state change.

## 6. Rollback and failure rules

Rollback is permitted only if the forward-created application is safely
attributable to this exact attempt and the fresh GET state still matches the
reviewed created shape.

The only predeclared inverse is:

`DELETE /accounts/{account_id}/access/apps/{created_app_id}`

After rollback, a fresh GET must prove the `warp` application count returned to
zero.

If the POST returns an HTTP/API error, the created object cannot be attributed
unambiguously, multiple `warp` applications appear, or any unrelated diff is
observed:

**STOP. Do not retry. Do not guess an application ID. Do not issue DELETE.**

A later recovery path requires fresh GET reconciliation and a new owner
authorization.

## 7. Authorization boundary

This source contract authorizes no Cloudflare mutation.

Merge of this source work does not authorize:

- application creation or policy editing;
- owner-phone enrollment;
- posture-rule changes;
- Dashboard or Control `Require Gateway`;
- session changes;
- Tunnel/DNS/Worker changes;
- RPi5 host/runtime mutation.

After merge and exact-main CI, the next safe live step is a new GET-only
`p1d-00` preflight. Only its fresh result can establish whether `p1d-01a` is
still the exact next state-changing gate.
