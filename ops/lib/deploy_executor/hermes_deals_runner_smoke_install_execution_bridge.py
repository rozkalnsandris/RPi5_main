from __future__ import annotations

from typing import Any, Mapping

from .hermes_deals_runner_smoke_install import (
    ApplyReceipt,
    AuthorizationConsumer,
    FixedInstallBackend,
    apply_install,
)
from .hermes_deals_runner_smoke_install_consumer import (
    CanonicalRunnerSmokeInstallRevalidator,
    prepare_install_live_envelope,
)

IMPLEMENTATION_ISSUE = 534


def execute_install_for_authorization(
    authorization_issue_number: int,
    *,
    canonical_revalidator: CanonicalRunnerSmokeInstallRevalidator,
    authorization_consumer: AuthorizationConsumer,
    backend: FixedInstallBackend,
) -> ApplyReceipt:
    """Bridge one canonical LIVE-AUTH issue to the fixed installer.

    Only the positive issue number is caller authority. The three keyword-only
    dependencies are trusted capability adapters supplied by a later separately
    reviewed LIVE wrapper; no caller-selected envelope, command, path, argv,
    environment, identity, hash, SHA, target, or mutation plan crosses this API.
    """

    envelope = prepare_install_live_envelope(
        authorization_issue_number,
        canonical_revalidator=canonical_revalidator,
    )
    return apply_install(
        envelope,
        authorization_consumer=authorization_consumer,
        backend=backend,
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "execution_bridge_implemented": True,
        "request_authority": ("authorization_issue_number",),
        "canonical_revalidation_immediately_before_apply": True,
        "fixed_apply_target": "hermes_deals_runner_smoke_install.apply_install",
        "prebuilt_live_envelope_allowed": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "caller_identity_allowed": False,
        "caller_hash_or_sha_allowed": False,
        "caller_target_or_operation_allowed": False,
        "caller_mutation_sequence_allowed": False,
        "external_entrypoint_enabled": False,
        "runtime_activation_enabled": False,
        "global_executor_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
