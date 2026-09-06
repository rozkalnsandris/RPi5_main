from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

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
from .registry import load_registry
from .transport import GitHubHttpsSender, GitHubRestClient

ISOLATED_AUTH_PATH = Path('/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json')
REGISTRY_PATH = Path('/etc/rozkalns-deploy-executor-p9/executor-operations.json')
EXECUTOR_CREDENTIAL_PATH = Path('/etc/rozkalns-deploy-executor/github-app.pem')
BROKER_RUNTIME_FACTORY_IMPLEMENTED = True
BROKER_ENTRYPOINT_WIRED = True
LIVE_INSTALL_ELIGIBLE = False
PRODUCTION_MUTATION_STARTED = False
REPLAY_STATE_DIRECTORY = Path('/var/lib/rozkalns-deploy-executor-p9')


class HermesDealsOriginBrokerRuntimeError(RuntimeError):
    pass


def _require_registry(registry: Any) -> Any:
    if getattr(registry, 'execution_enabled', None) is not False:
        raise HermesDealsOriginBrokerRuntimeError('runtime registry must remain execution-disabled')
    matches = [
        operation for operation in getattr(registry, 'operations', ())
        if (
            getattr(operation, 'operation_id', None) == OPERATION_ID
            and getattr(operation, 'source_repository', None) == SOURCE_REPOSITORY
            and getattr(operation, 'target_alias', None) == TARGET_ALIAS
            and getattr(operation, 'adapter_id', None) == ADAPTER_ID
        )
    ]
    if len(matches) != 1:
        raise HermesDealsOriginBrokerRuntimeError('runtime registry Hermes capability identity drifted')
    return registry


def build_runtime_broker_composition() -> HermesDealsOriginBrokerComposition:
    """Build the fixed root broker composition with no caller-selected authority."""

    if os.geteuid() != 0:
        raise HermesDealsOriginBrokerRuntimeError('runtime broker requires root process identity')
    try:
        auth_surface = load_contract(ISOLATED_AUTH_PATH)
        require_isolated_auth_surface(auth_surface)
        registry = _require_registry(load_registry(REGISTRY_PATH))
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
        'registry_path': str(REGISTRY_PATH),
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
