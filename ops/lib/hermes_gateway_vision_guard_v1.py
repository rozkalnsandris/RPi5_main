"""Source-only Hermes Gateway image ingress and final-transport guard candidate.

UNINSTALLED: never monkeypatches Hermes, imports credentials, sends network
requests, accesses host configuration or processes real media. This module
exposes an explicit Gateway ingress adapter and the *handle_request* seam used
by the actual HTTPX transport interface. Offline mocks prove boundary behavior;
installed code/protocol version and no-hidden-retry transport remain NOT_READY.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from hermes_synthetic_vision_probe_v1 import (
    FIXTURE_REF, IMAGE_MODE, MODEL, PROVIDER, synthetic_request,
)

# Public NousResearch/hermes-agent commit, NOT an installed-host source identity.
UPSTREAM_COMMIT = "c627ec84664d43e0b18b95d9d86d8963747d56c7"
UPSTREAM_BLOBS = {
    "gateway/run_inbound.py": "e5d71a8172d9c0b59669d70c1c52273e5d50a01e",
    "tools/vision_tools.py": "ad6acbc06fba076baeb3efeeb9a2c23db2a6c0e3",
    "agent/auxiliary_client.py": "34401444a875280deec8fb4f8e49cb38e3a6cf65",
    "agent/image_routing.py": "763f20a56606da77bda318773ec8c9d6d381fd6d",
}
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_BODY = 24_000


class NotReady(RuntimeError):
    """Source provenance or transport certification has not passed."""


class BoundaryRejected(ValueError):
    """User media, routed model, payload or dispatch violates the fixture."""


def verify_source_pin(revision: str, blobs: Mapping[str, str] | None) -> None:
    """Validate supplied public Git blob identities; do NOT inspect a host.

    The caller must separately prove identities originate from the installed
    tree. Passing literal values here is NOT actual host provenance.
    """
    if type(revision) is not str or revision != UPSTREAM_COMMIT:
        raise NotReady("INSTALLED_REVISION_UNVERIFIED")
    if type(blobs) is not dict or blobs != UPSTREAM_BLOBS:
        raise NotReady("INSTALLED_BLOBS_UNVERIFIED")


def gateway_ingress_envelope(
    *, image_refs: tuple, image_mode: str, provider: str, model: str,
    installed_revision: str, installed_blobs: dict,
) -> dict[str, Any]:
    """Strict gateway-media boundary: check *metadata* before content access.

    Never accept a platform file, path, URL, session media, second image or a
    native/main-model route. A synthetic marker is not an actual user upload.
    """
    verify_source_pin(installed_revision, installed_blobs)
    if type(image_refs) is not tuple or image_refs != (FIXTURE_REF,):
        raise BoundaryRejected("NON_SYNTHETIC_OR_FANOUT")
    if (image_mode, provider, model) != (IMAGE_MODE, PROVIDER, MODEL):
        raise BoundaryRejected("UNAPPROVED_IMAGE_ROUTE")
    return synthetic_request()


def require_fixed_http_request(request: Any) -> None:
    """Validate exactly one OpenRouter chat-completions POST + frozen JSON.

    The expected request is fully synthetic. No tokens, URL paths, prompts or
    model parameters may be supplied by the Gateway or the user.
    """
    if getattr(request, "method", None) != "POST":
        raise BoundaryRejected("HTTP_METHOD")
    if str(getattr(request, "url", "")) != ENDPOINT:
        raise BoundaryRejected("HTTP_TARGET")
    body = getattr(request, "content", None)
    if type(body) is not bytes or len(body) > MAX_BODY:
        raise BoundaryRejected("HTTP_PAYLOAD_SIZE_OR_TYPE")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise BoundaryRejected("HTTP_PAYLOAD_FORMAT") from None
    if type(value) is not dict or value != synthetic_request():
        raise BoundaryRejected("HTTP_PAYLOAD_NOT_FIXED")


class OfflineSingleDispatchHttpTransport:
    """HTTPX transport-shaped seam; constructed only for an OFFLINE test double.

    handle_request is the actual HTTPX/HTTPX2 transport entrypoint, *not*
    Hermes' high-level vision tool or its async_call_llm wrapper. This adapter
    proves only one delegate invocation. The delegate may still retry on its
    own, so no live transport is accepted without an independent no-retry
    attestation for the actual installed HTTPX/HTTPX2 and OpenAI SDK versions.
    """

    def __init__(self, delegate: Any, *, transport_class: str = "OFFLINE_MOCK"):
        if transport_class != "OFFLINE_MOCK":
            raise NotReady("LIVE_TRANSPORT_NOT_CERTIFIED")
        if not callable(getattr(delegate, "handle_request", None)):
            raise NotReady("MISSING_TRANSPORT_BOUNDARY")
        self._delegate = delegate
        self._spent = False

    @property
    def transport_entries(self) -> int:
        return int(self._spent)

    def handle_request(self, request: Any) -> Any:
        if self._spent:
            raise BoundaryRejected("SECOND_HTTP_DISPATCH")
        require_fixed_http_request(request)
        # Always consume *before* calling the transport: errors, timeouts,
        # reentrance, empty responses and 4xx/5xx must never be retried here.
        self._spent = True
        return self._delegate.handle_request(request)


def require_live_transport_readiness(*, installed_provenance_verified: bool,
                                     outbound_sdk_retry_setting: int,
                                     http_transport_retries: int,
                                     gateway_retry_suppressed: bool) -> None:
    """Unconditionally deny LIVE use until the actual vendor binding is built.

    No code in this repository is installed at the Gateway boundary yet.
    Numeric retry flags alone do not prove SDK or transport implementation.
    """
    raise NotReady("VENDOR_GATEWAY_INTEGRATION_NOT_INSTALLED")
