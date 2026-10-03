# Cloudflare Tunnel operator v1

Status: **SOURCE-DEFINED / CREDENTIAL NOT YET PROVISIONED**  
Initial consumer: `RPi5_main#819`  
Machine contract: `ops/contracts/cloudflare-tunnel-operator-v1.json`

## Purpose

RPi5_main uses one durable Cloudflare Tunnel capability credential for reviewed Tunnel operations across current and future projects.

The credential is scoped to the reviewed Cloudflare account and carries only:

`Cloudflare Tunnel Write`

This is intentionally broader than a read-only token so the same Tunnel capability can support future reviewed create/update/delete/configuration operations without minting a new token per project or per workflow.

It is **not** a general Cloudflare credential. DNS, Access and API-token-management permissions remain separate capabilities.

## Stable GitHub secret aliases

The source contract uses stable repository-secret names:

- `CLOUDFLARE_TUNNEL_ACCOUNT_ID`
- `CLOUDFLARE_TUNNEL_API_TOKEN`

Secret values must never be committed to Git, issues, PRs, documentation, chat, CI output or sanitized evidence.

Rotating or replacing the Cloudflare token preserves these aliases, so reviewed consumers do not require source rewiring.

## Permission boundary

The Cloudflare token is account-scoped and Tunnel-only.

Explicitly excluded from this credential:

- DNS permission;
- Access permission;
- API Tokens Read/Write/Edit;
- unrelated Cloudflare account capabilities.

Current Cloudflare documentation identifies `Cloudflare Tunnel Write` as an account permission for Tunnel management and accepts it for Tunnel read/configuration endpoints as well as Tunnel create/update operations.

Official references:

- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/methods/list/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/
- https://developers.cloudflare.com/tunnel/get-started/

## Capability is not authority

Possession of the Tunnel token does not authorize arbitrary Cloudflare requests.

Every consumer must be source-reviewed and classified as either read-only or write.

### Read-only consumers

A read-only consumer:

- may use only `GET`;
- must freeze its allowed endpoint set;
- must reject caller-selected methods/endpoints/payloads;
- must emit only sanitized evidence;
- may require its own fresh owner authorization before execution.

The initial consumer is `phase4-admin-route-origin-read-v1` for issue #819. It may call only:

- `GET /accounts/{account_id}/cfd_tunnel`;
- `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`.

Although the underlying token can write, this consumer cannot.

### Write consumers

A write consumer must have a separate reviewed source contract that freezes:

- operation identity;
- exact target;
- exact allowed method and endpoint;
- request-body construction;
- mutation budget;
- preflight;
- post-write verification;
- fail-closed recovery semantics.

A fresh explicit owner authorization is required before the first write. After a write starts, ambiguity or failure must STOP without undeclared retry, rollback, cleanup or alternate mutation.

There is no generic "run arbitrary Tunnel API request" interface.

## Shared capability boundaries

The same Tunnel credential may back reviewed GitHub and future host-side Tunnel consumers, but only inside this Tunnel capability.

The credential must not be reused for:

- Cloudflare Access;
- DNS;
- arbitrary account administration;
- API token creation/rotation;
- other repositories merely because their applications are routed through the RPi5 Tunnel.

Future projects should normally be onboarded by adding a reviewed consumer/operation in RPi5_main, not by copying the credential into each project repository.

## Provisioning and rotation

This source contract does not create the Cloudflare token and does not provision GitHub repository secrets.

Token creation and GitHub secret writes are separate owner-gated settings operations.

Rotation keeps the stable aliases `CLOUDFLARE_TUNNEL_ACCOUNT_ID` and `CLOUDFLARE_TUNNEL_API_TOKEN`. Consumers should not need source changes when only the underlying credential value rotates.

## Evidence boundary

Never emit or persist:

- API token value;
- Cloudflare account ID;
- Tunnel ID;
- raw Cloudflare payloads;
- private origin coordinates.

Consumers must reduce provider responses to their reviewed public-safe result schema.
