from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

from .github_app_auth import Requester, https_json_request
from .p9_source_auth import (
    HERMES_DEALS_SOURCE_REPOSITORY,
    HERMES_DEALS_SOURCE_REPOSITORY_ID,
    P9SourceInstallationTokenProvider,
    REQUIRED_PERMISSIONS,
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)

SOURCE_AUTH_COMPOSITION_IMPLEMENTED = True
SOURCE_RUNTIME_CREDENTIAL_PROVEN = False
SOURCE_RUNTIME_INSTALLATION_PROVEN = False
SOURCE_WRITE_PERMISSION_REQUIRED = False


def build_hermes_deals_source_token_provider(
    *,
    private_key: str | Path,
    requester: Requester = https_json_request,
    signer: Callable[[bytes, Path], bytes] | None = None,
) -> P9SourceInstallationTokenProvider:
    """Build the exact single-repository read-only source token provider.

    Repository identity and permissions are source-fixed by p9_source_auth.
    Callers cannot select a repository, repository ID or token permissions.
    Runtime credential/install state remains a later read-only LIVE preflight.
    """

    return P9SourceInstallationTokenProvider(
        repository=HERMES_DEALS_SOURCE_REPOSITORY,
        private_key=private_key,
        requester=requester,
        signer=signer,
    )


def source_readiness() -> Mapping[str, object]:
    return {
        "source_auth_composition_implemented": SOURCE_AUTH_COMPOSITION_IMPLEMENTED,
        "repository": HERMES_DEALS_SOURCE_REPOSITORY,
        "repository_id": HERMES_DEALS_SOURCE_REPOSITORY_ID,
        "app_id": SOURCE_APP_ID,
        "installation_id": SOURCE_INSTALLATION_ID,
        "requested_permissions": dict(REQUIRED_PERMISSIONS),
        "repository_selection_required": "selected",
        "token_repository_count": 1,
        "source_runtime_credential_proven": SOURCE_RUNTIME_CREDENTIAL_PROVEN,
        "source_runtime_installation_proven": SOURCE_RUNTIME_INSTALLATION_PROVEN,
        "source_write_permission_required": SOURCE_WRITE_PERMISSION_REQUIRED,
        "permission_mutation_authorized": False,
        "credential_mutation_authorized": False,
    }
