# Canonical ingress registry v1

Status: **source policy only**  
Roadmap: `RPi5_main#60`  
Implementation: `RPi5_main#814`  
Machine contract: `ops/contracts/ingress-registry-v1.json`

## Purpose

This contract gives `RPi5_main` one public-safe source registry for externally meaningful RPi5 ingress services. Every registered service has exactly one zone:

- `PUBLIC` — anonymous external access is intentional and Cloudflare Access must not be required.
- `ADMIN` — administrator access is required and the Access class is distinct from PRIVATE.
- `PRIVATE` — non-public application access is required and the Access class is distinct from ADMIN.

The registry is designed for later drift comparison. It records source policy and dated evidence classes; it is not a live inventory.

## Runtime-state boundary

`current_origin_class` means the latest accepted source or dated historical evidence classification available to the registry. It never means “observed on the host now”.

Every entry therefore carries `last_verified_evidence.runtime_current=false`. A future host/Cloudflare audit must collect fresh read-only evidence before making any statement about the current running listener, route, firewall, Access policy, container or service state.

Merging this source:

- does not prove current Cloudflare or RPi5 runtime state;
- does not authorize Cloudflare, Tunnel, DNS, firewall, Docker, systemd or bind/listener mutation;
- does not authorize protected-runtime access, credentials, secrets or permission changes;
- does not authorize Home Assistant configuration import/deploy;
- does not remediate drift.

Any remediation remains a separate exact owner-gated LIVE action.

## Origin classes

The machine contract uses only public-safe origin classes:

- `loopback`
- `lan`
- `other`
- `unknown`

No private IP address or internal origin port is stored in the registry. Historical V18 evidence remains referenced by document path rather than copied into this contract.

`desired_origin_class` is policy intent. It is not an instruction to mutate production.

## Ownership

Each service records two different owners:

- `runtime_owner` — the repository responsible for RPi5 host/runtime integration;
- `repository_owner` — the application/configuration repository that owns the service-level source.

The shared Cloudflare Tunnel lifecycle remains owned by `RPi5_main`.

`coloring.rozkalns.net` is registered as a PUBLIC, loopback-only Coloring Pages target owned at the application layer by `rozkalnsandris/coloring-pages`. Source registration records policy only: the Cloudflare route/DNS association remains absent until the separately authorized LIVE activation in `RPi5_main#841`.

## Access and LAN break-glass

`access_class` is one of `NONE`, `ADMIN`, or `PRIVATE`.

Invariants:

- PUBLIC => `access_required=false`, `access_class=NONE`, LAN break-glass forbidden.
- ADMIN => `access_required=true`, `access_class=ADMIN`.
- PRIVATE => `access_required=true`, `access_class=PRIVATE`.
- ADMIN and PRIVATE are never interchangeable.
- LAN break-glass is explicit: `required`, `allowed`, or `forbidden`.

The ADMIN services that retain LAN recovery semantics do so intentionally; this is not a blanket rule to expose all ADMIN services on LAN.

## #60 coverage and supersession

The registry covers every service named by #60 plus later reviewed RPi5-hosted services such as the RPi5 Dashboard and Coloring Pages.

One historical naming conflict is resolved explicitly: #60 called the Hermes application a PRIVATE service, while the newer desired-state contract `ops/contracts/cloudflare-hostname-policy.yaml` classifies `hermes.rozkalns.net` as ADMIN. Registry v1 follows the newer source policy and keeps the #60 name as a `roadmap_alias` so coverage is explicit rather than silently dropping the old roadmap item.

`control.rozkalns.net` is intentionally excluded from this RPi5 ingress registry because its runtime is a Cloudflare Worker, not an RPi5-hosted origin. Its source policy remains in `ops/contracts/cloudflare-hostname-policy.yaml`.

## Validation

`tests/test-ingress-registry-v1.py` enforces:

- schema and non-authorizing source semantics;
- unique service IDs and hostnames;
- exact #60 service coverage;
- zone/Access/LAN break-glass invariants;
- ADMIN/PRIVATE separation;
- origin-class enums;
- explicit runtime/repository ownership;
- alignment with the existing hostname policy;
- absence of private RFC1918/loopback coordinates and forbidden secret/credential surfaces.

The test is part of `make test` / `make validate`.

## Phase transition

This source outcome is the Phase 2 implementation for #60. Phase 2 becomes **COMPLETE only after** the canonical PR is merged and #60 continuity is updated against the exact merged SHA. Phase 3+ remain unselected and require their own fresh scope and, where applicable, separate LIVE authority.
