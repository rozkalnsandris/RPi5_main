# Hermes Option B — safe synthetic Gateway vision acceptance contract v1

Status: **SOURCE-ONLY DESIGN / NOT A LIVE ACTIVATION OR TEST RESULT**. Outcome issue: [#1330](https://github.com/rozkalnsandris/RPi5_main/issues/1330). Historical observed Hermes/OpenRouter provider smoke: [RPi5 health handoff §14](RPI5_HOST_HEALTH_2026-11-01.md). Any new Gateway, host, account or model/API action needs separate explicit owner authority.

## 1. Evidence boundary and public code references

The successful **direct Hermes auxiliary/OpenRouter client** synthetic 96×96 image test returned HTTP 200, recognized a red circle, and observed the NVIDIA `nvidia/nemotron-3.5-super-vl:free` SKU with an explicit zero-price routing cap. It did **not** invoke the Gateway media pipeline, prove Gateway one-dispatch behavior, prove actual account billing or authorize real/private images. The prior host file hash and Gateway PID were historic post-checks, **not** persistent live-state assertions.

Public source reviewed at **NousResearch/hermes-agent commit `c627ec84664d43e0b18b95d9d86d8963747d56c7`**:
- [`gateway/run_inbound.py`](https://github.com/NousResearch/hermes-agent/blob/c627ec84664d43e0b18b95d9d86d8963747d56c7/gateway/run_inbound.py): `_enrich_inbound_images` can choose **native** attachment to the current main model, or **text** mode with `_enrich_message_with_vision`. That helper loops over *every* incoming image path and calls `vision_analyze_tool` automatically; no owner-per-image authorization occurs at that function boundary.
- [`tools/vision_tools.py`](https://github.com/NousResearch/hermes-agent/blob/c627ec84664d43e0b18b95d9d86d8963747d56c7/tools/vision_tools.py): `vision_analyze_tool` resolves an image source to a temporary media file and invokes `async_call_llm`; on qualifying size errors it may resize and **dispatch again**. `_call_vision_llm` also **dispatches again** if the first response contains no extracted text. `_run_analysis` writes debug-session data through `DebugSession` and performs temporary-file cleanup. A single high-level tool call is **not** equivalent to a single external request or a no-write operation.
- [`tests/gateway/test_vision_preprocess.py`](https://github.com/NousResearch/hermes-agent/blob/c627ec84664d43e0b18b95d9d86d8963747d56c7/tests/gateway/test_vision_preprocess.py): existing **mocked** `_enrich_message_with_vision` test checks that a description reaches the user text; it does not cover protected image provenance, one-external-dispatch, retention, free-only routing or production sessions.

**Provenance limit:** this is public upstream source at the cited SHA, **not an assertion that the RPi5-installed Hermes tree uses it**. Before any implementation or live test, confirm exact installed source revision/file identity and trace the actual current media handler. Source-level findings must not be confused with current runtime process state.

## 2. Threat model / non-negotiable privacy boundary

The owner accepted NVIDIA logging/improvement processing and non-EU processing **for public or genuinely synthetic, non-confidential content only**. The separately owner-changed OpenRouter account policy (`All other models` ZDR **OFF**) is **account-wide**: it provides no automatic image-content allowlist. Ordinary Telegram/other Gateway attachments may include private/family/customer material; automatic text-mode vision enrichment may forward such material without another explicit selection. **Do not enable unrestricted real-image Gateway traffic on the strength of the direct SDK smoke.**

The main-model **native** image route is not necessarily the NVIDIA free auxiliary route. Reject or isolate it in a cost/privacy-bounded test unless separately proven appropriate and authorized. Auxiliary `free_only` covers its own routing and is not a whole-Gateway billing barrier. Zero-price model listings, a `:free` suffix and `provider.max_price` limits are not proofs of future zero invoices.

## 3. Required source and offline acceptance gates — before any LIVE authorization

1. **Pin actual installed-code provenance.** Verify a fixed source commit/tree and exact relevant source hashes through a separately permitted sanitized, source-only read. Abort on missing, unsupported or changed Gateway image ingress, router, `vision_analyze_tool`, retry helpers or provider client. Do not access private config, credentials, histories, session databases or process environments to discover source.
2. **Synthetic-only provenance at entry.** The test image must be generated in-memory by a deterministic fixture (e.g. 96×96 blue background, red circle). No user-provided path, URL, Telegram history, downloaded attachment, gallery photo, generic arbitrary-media argument or second image. A test-specific entrypoint should accept **only a hard-coded fixture identity** and a fixed prompt. Provenance must be enforced by code, not by prompt text or an LLM's choice.
3. **Routing is exact, not implied.** Resolve only `openrouter` plus `nvidia/nemotron-3.5-super-vl:free`. Abort on native/main-model path, another SKU/provider, fallback route, stale source/config identity or nonzero provider price. The request must explicitly use zero `max_price` for prompt, completion, image and request; disable SDK/provider retries and any implicit paid fallback. Do not alter account privacy settings or protected host config.
4. **One outbound dispatch across every layer.** A shared guard must fail-closed *before* a second actual external dispatch, including `async_call_llm` retries, empty/reasoning-only responses, image-size exceptions, model fallback, connection retries and any gateway-level retry. Merely calling `vision_analyze_tool` once, setting SDK `max_retries=0` in a different client, or counting completed responses is insufficient. If this cannot be enforced on the installed source without modification, classify **NOT READY**.
5. **Constrain side effects.** Before an actual Gateway path, enumerate temporary media/cache/debug writes, inbound session/message state writes, any outbound chat/reply and cleanup behavior. Treat production writes, chat transport and service mutation as separate LIVE classes; no test mutation/rollback/cleanup without its own frozen authorization. Prefer mocked, offline Gateway enrichment tests first. Suppress raw data-URL bytes, private paths, prompts and provider errors from logs/evidence; emit only sanitized counts and PASS/STOP reason categories.
6. **Offline, deterministic proof.** With external network calls stubbed to fail if reached, demonstrate that the **Gateway ingress-to-enrichment function** receives exactly one synthetic image, calls the test-owned guarded adapter once, returns the expected short visual classification, and exercises both routing branches under a non-live fixture. This is a *mocked source integration proof*, not a successful OpenRouter response. Do not use the live Telegram account, Gateway session DB or host service for this stage.

## 4. Negative tests required for acceptance

| Case | Expected gate result |
| --- | --- |
| Exactly one deterministic synthetic image, fixed public-safe prompt, mocked response `RED` | Offline PASS; one guarded dispatch invocation, no network |
| Arbitrary local image path / external URL / private image / unsupported data URI | STOP before source read, disk write or API dispatch |
| More than one image, or any Gateway tool fan-out | STOP before first outbound request |
| Installed-source identity unknown, changed or incompatible | STOP before dispatch; no best-effort fallback |
| Main/native model routing, different/free-looking SKU, unknown provider or paid fallback | STOP before dispatch |
| First response empty/reasoning-only, image-size error, 429, transport failure or request timeout | At most **one** outbound request; STOP, never retry |
| OpenRouter price-cap unsupported/omitted or provider cannot guarantee the pinned route | STOP before dispatch |
| Debug/cache/session/chat side effect not enumerated in exact LIVE scope | STOP before production mutation |
| Unexpected external network call in offline test | Immediate test failure; no network allowed |

## 5. Separate owner gates and evidence contract

**Current gate:** this document defines the bounded source contract; it does **not** implement a protected Gateway transport, enforce a runtime media allowlist, ship an isolated test harness, or verify any present RPi5 deployment. The safe next engineering task is **source-level implementation and isolated tests** of the single-dispatch synthetic adapter at the actual pinned Hermes Gateway integration boundary; if that requires modifying a different repository or vendor-controlled code, verify the exact source ownership and seek scope-specific authorization before writing.

Any later RPi5/Gateway/API/Telegram test requires **separate exact owner LIVE authority**, binding installed SHA, exact target, fixed synthetic fixture, selected route/model, allowed temporary/session/chat mutations (if any), **one maximum external request**, zero-price cap, no retries or rollback, and sanitized result. Before dispatch run a fresh fail-closed preflight. On first mutation/tool error/timeout/drift, preserve only safe read-only evidence and STOP; no retries, cleanup or alternative path without new authority.

**Source-only conclusion:** direct NVIDIA free auxiliary-client smoke **PASS**; automatic Gateway image ingress and one-dispatch/only-synthetic policy **UNPROVEN**; unrestricted Gateway image forwarding **not approved**. No new provider request, service restart, host write or Gateway end-to-end test was carried out to create this contract.
