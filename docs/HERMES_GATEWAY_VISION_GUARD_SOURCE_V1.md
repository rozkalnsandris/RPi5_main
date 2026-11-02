# Hermes Gateway Option B — pinned-source offline ingress/HTTP transport adapter v1

**Issue:** [#1338](https://github.com/rozkalnsandris/RPi5_main/issues/1338).  
**State:** SOURCE-ONLY MOCKED CONTRACT. **LIVE / installed Gateway vision = NOT_READY.**  
**Related:** [synthetic Gateway gate](HERMES_GATEWAY_SYNTHETIC_VISION_GATE_V1.md), [single-callback fixture](HERMES_SYNTHETIC_VISION_OFFLINE_PROBE_V1.md), and [2026-11-01 RPi5 health evidence](RPI5_HOST_HEALTH_2026-11-01.md) §14.

## Exact public-source provenance, NOT installed-source evidence

Public owner: `NousResearch/hermes-agent`, immutable revision `c627ec84664d43e0b18b95d9d86d8963747d56c7`. Expected **Git blob SHA-1 IDs** at that revision:

| File | Blob ID | Exact source boundary |
| --- | --- | --- |
| [`gateway/run_inbound.py`](https://github.com/NousResearch/hermes-agent/blob/c627ec84664d43e0b18b95d9d86d8963747d56c7/gateway/run_inbound.py) | `e5d71a8172d9c0b59669d70c1c52273e5d50a01e` | `_enrich_inbound_images` / `_enrich_message_with_vision`, chooses native or text and auto-runs image analysis |
| [`tools/vision_tools.py`](https://github.com/NousResearch/hermes-agent/blob/c627ec84664d43e0b18b95d9d86d8963747d56c7/tools/vision_tools.py) | `ad6acbc06fba076baeb3efeeb9a2c23db2a6c0e3` | `vision_analyze_tool`, `async_call_llm` size/empty retry, temp files and debug |
| [`agent/auxiliary_client.py`](https://github.com/NousResearch/hermes-agent/blob/c627ec84664d43e0b18b95d9d86d8963747d56c7/agent/auxiliary_client.py) | `34401444a875280deec8fb4f8e49cb38e3a6cf65` | Auxiliary provider resolution and model calls |
| [`agent/image_routing.py`](https://github.com/NousResearch/hermes-agent/blob/c627ec84664d43e0b18b95d9d86d8963747d56c7/agent/image_routing.py) | `763f20a56606da77bda318773ec8c9d6d381fd6d` | Native versus text image route |

Git blob identity is **not** a SHA-256 file hash. `verify_source_pin` only validates supplied identity metadata; **it does not read or attest the installed host tree**. A caller could supply constants without inspecting the host, therefore even a passing offline identity test must not be reported as host-integrity proof.

Vendor docs:
- [Hermes vision/image routing](https://hermes-agent.nousresearch.com/docs/user-guide/features/vision) confirms native/auxiliary split and session media caching/replay.
- [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection) documents `allow_fallbacks` and `max_price`; these filter routing and do not prove future zero charges.
- [OpenAI Python SDK](https://github.com/openai/openai-python/blob/main/README.md) documents default retries and `max_retries=0`; the [HTTPX2 transition](https://github.com/openai/openai-python/blob/main/httpx2.md) means actual installed SDK/transport versions matter. Do not assume the current installed Hermes uses legacy `httpx` rather than `httpx2`.

## Repository-owned, OFFLINE seams

`ops/lib/hermes_gateway_vision_guard_v1.py` is not imported, installed or injected into the vendor Gateway. It imports only the existing deterministic fixture in `ops/lib/hermes_synthetic_vision_probe_v1.py`.

1. **`gateway_ingress_envelope`:** checks the supplied upstream commit and exact file blobs, then checks *metadata first*. The sole accepted tuple is `(synthetic:hermes-option-b-red-circle-v1,)`, the sole mode is `text` and the route is exactly `openrouter` + `nvidia/nemotron-3.5-super-vl:free`. Files, URLs, data URIs, multiple attachments, a real upload, main-model `native` routing or different providers/SKUs fail before any file content is read. It generates exactly one fixed synthetic PNG+prompt+zero-price-cap request, regardless of an external message/prompt.
2. **`require_fixed_http_request`:** asserts the **transport-entry** method, URL and complete JSON body against the frozen synthetic request. No arbitrary prompt, extra model parameter, different endpoint, paid SKU or provider fallback can pass. This is intentionally stricter than a normal OpenAI SDK request; a future SDK-generated body must be proven byte/semantic-compatible or **fail closed**.
3. **`OfflineSingleDispatchHttpTransport.handle_request`:** a duck-typed HTTPX transport-entry seam that consumes its one entry **before** calling one offline mock delegate. Its negative tests cover reentrance, timeouts, failures and no retry after any result. It rejects all production transport claims (`transport_class != OFFLINE_MOCK`). **One mock delegate call is not one verified outbound HTTP wire request**: the delegate might internally retry, and the installed Gateway might bypass the wrapper.
4. **`require_live_transport_readiness`:** intentionally raises `VENDOR_GATEWAY_INTEGRATION_NOT_INSTALLED` for all inputs. Do not weaken this to turn a mock PASS into a LIVE READY marker.

`tests/test-hermes-gateway-vision-guard-v1.py` is wired into `make test` / `make validate`. Tests are deterministic and use no provider SDK, keys, session DB, cached media, network, vendor service or host. The successful outcomes are **offline mocks only**.

## Unresolved actual integration / owner gates

**Host code & trust:** Verify exact installed source revision and relevant files via a **separately authorized, sanitized, source-only** RPi5 read; do not inspect process env, app config, credentials or user data. If a different revision is installed, stop and review actual ingress, routing, adapter and outbound code before any patch proposal.

**Vendor integration:** The real `GatewayRunner._enrich_inbound_images` can iterate over arbitrary cached message-media paths and write sessions/cache before the auxiliary client call. The source-owned fixture marker cannot become a trusted user Telegram message; the synthetic fixture must be injected through a dedicated owner-authorized test seam **before** ordinary media download, cache, persistence, or automatic native/auxiliary forwarding. No production Gateway hook exists yet in this repository. No user-upload whitelist is in force. Unrestricted image forwarding remains unapproved.

**HTTP dispatch:** The installed OpenAI SDK may retry unless `max_retries=0` is bound **to that exact client**, with provider fallbacks disabled, HTTP transport retry count zero, and every Gateway/vision size/empty-response retry path bypassed or guarded. The actual SDK may use HTTPX2 rather than HTTPX; the current offline mock does **not** certify that wiring. Reuse of `vision_analyze_tool` alone does not satisfy the one-dispatch requirement.

**Side-effects:** A real chat Gateway path may write inbound photo caches, vision temp/normalized image files, debug trace metadata, session/history/native-image replay, notifications and outbound replies. Each is a potential production-data/transport mutation. No such writes are within #1338 source authority. Account-wide OpenRouter ZDR OFF also fails to enforce the owner's public/synthetic-only privacy scope; private/family/customer images remain outside approval.

**Later LIVE gate:** Separately authorize a pinned RPi5 installed-source inspection and, *only after source reconciliation and an owner-reviewed dedicated seam*, a frozen single synthetic image to the exact free NVIDIA route, with zero price cap, no provider/SDK/transport/Gateway retries, explicit bounded cache/session/reply semantics, no cleanup/rollback retries and sanitized evidence. This source PR neither executes nor grants any of those operations.

## Current evidence-based result

- Offline ingress boundary and transport-entry guard: **IMPLEMENTED AS UNINSTALLED TEST ADAPTER**, conditional on supplied public-source identifiers.
- Actual installed Gateway source, real ingress interception, live transport's internal retry semantics, live session effects and end-to-end picture recognition: **NOT VERIFIED**.
- **NO LIVE MUTATIONS, EXTERNAL IMAGE DISPATCHES, PRIVATE MEDIA OR VENDOR REPO WRITES** were used to produce this source change.
