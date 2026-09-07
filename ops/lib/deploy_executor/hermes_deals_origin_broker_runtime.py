from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .hermes_deals_origin_adapter import ADAPTER_ID, OPERATION_ID, SOURCE_REPOSITORY, TARGET_ALIAS
from .hermes_deals_origin_broker_composition import HermesDealsOriginBrokerComposition
from .hermes_deals_origin_canonical_revalidator import ConcreteCanonicalHermesOriginRevalidator
from .hermes_deals_origin_helper_launch import run_fixed_helper_process
from .hermes_deals_origin_host_evidence import ConcreteSanitizedHermesOriginHostEvidenceResolver
from .hermes_deals_origin_runtime_adapters import (
    ConcreteDurableHermesOriginReplayAuthority,
    ConcreteLocalHermesOriginHostObservationProvider,
)
from .hermes_deals_origin_source_auth import (
    SOURCE_CREDENTIAL_PATH,
    build_hermes_deals_source_token_provider,
)
from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .registry import BaselineContract, MutationBudget, OperationRegistry, OperationSpec, QueueMatch
from .transport import GitHubHttpsSender, GitHubRestClient

ISOLATED_AUTH_PATH = Path('/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json')
EXECUTOR_CREDENTIAL_PATH = Path('/etc/rozkalns-deploy-executor/github-app.pem')
BROKER_RUNTIME_FACTORY_IMPLEMENTED = True
BROKER_ENTRYPOINT_WIRED = True
LIVE_INSTALL_ELIGIBLE = False
PRODUCTION_MUTATION_STARTED = False
REPLAY_STATE_DIRECTORY = Path('/var/lib/rozkalns-deploy-executor-p9')
FIXED_RUNTIME_REGISTRY_IMPLEMENTED = True


class HermesDealsOriginBrokerRuntimeError(RuntimeError):
    pass


def _fixed_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=TARGET_ALIAS,
            execution_location_class='trusted-home-host',
            repository_entrypoint='tools/runner/origin-path-rpi5-audit-dispatcher.sh',
            deploy_class='STRICT_LIVE_AUTH_REQUIRED',
        ),
        target_alias=TARGET_ALIAS,
        adapter_id=ADAPTER_ID,
        authorization_class='STRICT',
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(
            kind='resolver',
            resolver_id='hermes-deals.origin-path-registration.v1',
        ),
        mutation_budget=(
            MutationBudget(
                category='hermes-deals.read-only-audit-invocation',
                max_operations=1,
            ),
        ),
        rollback_policy='NONE',
        exclusions=(
            'production database writes',
            'production deployment/cutover',
            'restart/configuration mutation',
            'parser/collector behavior changes',
            'runner registration/deregistration',
            'GitHub App/credential/permission changes',
        ),
        dependencies=(
            'source-repository-id:1317143994',
            'migration-contract:hermes-deals#787',
            'workflow-source-blob:99a18c5f669e7880a8a8288c3f964285df87ae22',
            'dispatcher-source-blob:f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc',
            'installer-source-blob:41f004420a0f5aed314aaefd796a54e14dbd17ea',
            'probe-source-blob:2362e8eb578a7279c38fe4ed2a7d1edd05df891a',
            'pull-helper-source-blob:4ef95c3f02b810b6b25721aa1b1b53d43b8ca572',
            'pull-helper-capability:origin-path-audit',
            'pull-helper-registration-schema:rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1',
            'pull-helper-evidence-schema:rozkalns.hermes-deals.origin-path-rpi5-pull-evidence.v1',
            'pull-helper-machine-id:rpi5',
            'pull-helper-arguments:registered_source_sha,as_of',
            'privileged-boundary:identity-only-dispatch-request-v1',
        ),
        preflight=(
            'LIVE-AUTH and READY queue envelope are independently revalidated before any privileged request',
            'source repository stable ID is 1317143994 and authorized SHA is merged/reachable from current main',
            'exact authorized source SHA CI is successful',
            'origin-path workflow dispatcher installer and probe source blobs match the reviewed Hermes Deals identities',
            'runner-independent pull helper blob capability schemas machine identity and two-argument interface match the reviewed Hermes Deals contract',
            'root-owned registration is independently revalidated without taking command/path/argv authority from GitHub prose',
            'poller remains unprivileged and sends identity only across the privileged boundary',
            'operation remains execution-disabled with rollback policy NONE and one read-only audit invocation maximum',
        ),
        postconditions=(
            'sanitized dispatcher manifest is bound to authorized commit SHA and requested as-of date',
            'production_apply_authorized is false',
            'production_database_write is false',
            'production_deployment is false',
            'restart_or_configuration_mutation is false',
            'reporting failure cannot authorize or replay a second execution',
        ),
        required_github_evidence=(
            'source repository stable identity',
            'authorized SHA is merged/reachable from current main',
            'exact-SHA CI completed successfully',
            'workflow dispatcher installer and probe source blobs match the audited Hermes Deals identities',
            'runner-independent pull helper source and interface match the audited Hermes Deals identities',
            'LIVE-AUTH and READY queue remain separate authority and eligibility records',
        ),
    )
    return OperationRegistry(
        schema_version=1,
        execution_enabled=False,
        operations=(operation,),
    )


def build_runtime_broker_composition() -> HermesDealsOriginBrokerComposition:
    """Build the fixed root broker composition with no caller-selected authority."""

    if os.geteuid() != 0:
        raise HermesDealsOriginBrokerRuntimeError('runtime broker requires root process identity')
    try:
        auth_surface = load_contract(ISOLATED_AUTH_PATH)
        require_isolated_auth_surface(auth_surface)
        registry = _fixed_registry()
        sender = GitHubHttpsSender()
        read_clients = build_p9_read_clients(
            auth_surface=auth_surface,
            private_key=EXECUTOR_CREDENTIAL_PATH,
            sender=sender,
        )
        source_provider = build_hermes_deals_source_token_provider(
            private_key=SOURCE_CREDENTIAL_PATH,
        )
        source_client = GitHubRestClient(token_provider=source_provider, sender=sender)
        replay = ConcreteDurableHermesOriginReplayAuthority()
        revalidator = ConcreteCanonicalHermesOriginRevalidator(
            authorization_client=read_clients.authorization,
            queue_client=read_clients.queue,
            source_client=source_client,
            auth_surface=auth_surface,
            registry=registry,
            replay_availability=replay,
        )
        host_resolver = ConcreteSanitizedHermesOriginHostEvidenceResolver(
            observation_provider=ConcreteLocalHermesOriginHostObservationProvider(),
        )
        return HermesDealsOriginBrokerComposition(
            canonical_revalidator=revalidator,
            host_evidence_resolver=host_resolver,
            replay_authority=replay,
            runner=run_fixed_helper_process,
        )
    except HermesDealsOriginBrokerRuntimeError:
        raise
    except Exception:
        raise HermesDealsOriginBrokerRuntimeError('runtime broker composition failed closed') from None


def source_readiness() -> Mapping[str, object]:
    return {
        'broker_runtime_factory_implemented': BROKER_RUNTIME_FACTORY_IMPLEMENTED,
        'factory_arguments': (),
        'isolated_auth_path': str(ISOLATED_AUTH_PATH),
        'fixed_runtime_registry_implemented': FIXED_RUNTIME_REGISTRY_IMPLEMENTED,
        'global_registry_path_used': False,
        'fixed_runtime_registry_operation_count': 1,
        'executor_credential_path': str(EXECUTOR_CREDENTIAL_PATH),
        'source_credential_path': SOURCE_CREDENTIAL_PATH,
        'caller_repository_selector_allowed': False,
        'caller_path_command_argv_environment_allowed': False,
        'shared_durable_replay_authority': True,
        'durable_replay_consume_before_helper': True,
        'replay_state_directory': str(REPLAY_STATE_DIRECTORY),
        'replay_state_write_required_for_dispatch': True,
        'current_service_replay_write_authority_proven': False,
        'broker_entrypoint_wired': BROKER_ENTRYPOINT_WIRED,
        'live_install_eligible': LIVE_INSTALL_ELIGIBLE,
        'production_mutation_started': PRODUCTION_MUTATION_STARTED,
    }
