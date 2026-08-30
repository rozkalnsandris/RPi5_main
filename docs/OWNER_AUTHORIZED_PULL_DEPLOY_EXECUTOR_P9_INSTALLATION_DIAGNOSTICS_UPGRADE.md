# Owner-authorized P9 source-App installation diagnostics upgrade

This document defines the reviewed **source-only** follow-up to the consumed Gate B
source-App capability proof recorded in canonical issue `#191`.

The failed Gate B receipt stopped at the sanitized stage
`installation_response`, after the exact Control repository installation GET was
attempted and before installation scope validation or installation-token mint.
That authorization is consumed and must not be retried.

## Source change

`ops/lib/deploy_executor/p9_source_auth.py` retains the exact repository-specific
probe:

`GET /repos/rozkalnsandris/rozkalns-control-center/installation`

The response is now classified into public-safe allowlisted stages:

- `installation_not_found`: HTTP 404 only; this is the expected provider class
  when the App is not installed for the exact repository or the repository is
  not in the installation's selected repository set;
- `installation_status`: any other non-200 response;
- `installation_payload`: HTTP 200 with a non-object payload;
- `installation_scope`: HTTP 200 object that fails the existing exact
  installation/App/owner/selected-repository/read-only permission contract.

No response body, provider message, JWT, private-key material, installation
token, or raw exception text is included in these stages.

The token mint remains unreachable unless the exact repository installation
response is HTTP 200, object-shaped, and passes the existing strict scope
validation.

## Reviewed host upgrade operator

After a future explicit MERGE and exact-main CI, a **separate LIVE
authorization** may run:

`scripts/install-deploy-executor-p9-installation-diagnostics-upgrade.py`

The operator is preflight-only unless `--apply` is supplied. It accepts one
exact reviewed `RPi5_main` SHA and replaces exactly one installed file:

`/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py`

Expected installed prestate is the Gate A reviewed blob:

`2b1fc728453aca32631be9ffe8af127523b14e3b`

Required installed metadata remains root:root mode `0644`.

The operator:

- requires checkout `HEAD` to equal the supplied reviewed SHA;
- verifies the operator itself against that exact SHA;
- obtains replacement bytes from the immutable Git object at that SHA;
- validates the target and every parent directory before mutation;
- revalidates the opened inode, metadata, and old bytes before the first
  `ftruncate`;
- writes in place only and verifies exact reviewed bytes through the same file
  descriptor;
- has no temp-file/rename/unlink, retry, cleanup, or rollback path.

It does **not** modify the baseline CLI and does not perform any network,
credential, D1, baseline, P9, StateStore, systemd, service, timer, or
config/registry operation.

Expected preflight markers:

- `P9_INSTALLATION_DIAGNOSTICS_UPGRADE_PREFLIGHT=PASS`
- `P9_INSTALLATION_DIAGNOSTICS_MUTATION=NO`

Expected successful apply markers include:

- `P9_INSTALLATION_DIAGNOSTICS_UPGRADE=PASS`
- `TARGETS_REPLACED=1`
- `BASELINE_CLI_TOUCHED=NO`
- `NETWORK_REQUEST=NO`
- `CREDENTIAL_READ=NO`
- `P9_EXECUTION=NO`
- `STATE_STORE_TOUCHED=NO`
- `SYSTEMD_MUTATION=NO`
- `CONFIG_REGISTRY_MUTATION=NO`
- `ROLLBACK_PATH=NO`

## Authorization boundary

Source review or merge does not authorize `--apply` and does not authorize a
new Gate B capability proof.

After the diagnostics source is merged and separately installed, a new Gate B
canary still requires its own explicit LIVE authorization. If the canary
returns `installation_not_found`, STOP. Adding Control to the GitHub App's
selected repositories, changing repository selection, or widening App
permissions is a separate trust-surface mutation and is not implied by this
upgrade.
