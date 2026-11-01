# Hermes Option B — offline synthetic vision probe v1

Issue: [#1334](https://github.com/rozkalnsandris/RPi5_main/issues/1334).
Prerequisite risk contract: [Gateway synthetic vision gate v1](HERMES_GATEWAY_SYNTHETIC_VISION_GATE_V1.md).
Historical successful **direct SDK** smoke: [RPi5 health handoff §14](RPI5_HOST_HEALTH_2026-11-01.md).

## What this implements

- \`ops/lib/hermes_synthetic_vision_probe_v1.py\` is a **pure-Python, uninstalled, offline-only test fixture and local callback seam**. No CLI, credentials, configuration reader, network client, session state, production permissions, service operations or Gateway integration.
- It produces a deterministic 96×96 synthetic RGB PNG **in memory**: blue background with one red central circle. It has one fixed prompt, one fixed auxiliary OpenRouter route and exactly \`nvidia/nemotron-3.5-super-vl:free\`. The only accepted incoming media is the internal fixture marker \`synthetic:hermes-option-b-red-circle-v1\`; real paths, data URLs, remote images, lists and multi-image input are rejected.
- The frozen request specifies a zero max-price cap for prompt/completion/image/request, no provider fallback and only that free SKU. The \`SingleUseSyntheticProbe\` consumes its allowed **one local callback attempt before calling the supplied mock sender**. Empty/wrong output, exceptions, timeouts and re-entrance cannot initiate a second callback using the same probe object.
- \`tests/test-hermes-synthetic-vision-probe-v1.py\` uses a **mock callback**, verifies image pixels, request construction, rejection matrix and one-use behavior. No external request is sent. The test is part of the normal \`make test\` / \`make validate\` CI sequence.

## Exact proof boundary — read before reuse

**This is NOT a Hermes Gateway integration, actual single-HTTP-dispatch enforcement, price guarantee, credential-free live gateway, or successful Telegram image acceptance.** A mock \`send\` callback can internally make multiple SDK/HTTP requests; the offline single-use guard proves **one callback entry only**. It also does not change the vendor's automatic image enrichment, its main-model native path, or its size/empty-response retry branches.

The source files that implement the real Gateway image routing are in external \`NousResearch/hermes-agent\`. The public-source analysis in the prerequisite contract pinned \`c627ec84664d43e0b18b95d9d86d8963747d56c7\`, **not the installed RPi5 source revision**. In particular:
- \`gateway/run_inbound.py\`: the auto image-enrichment / native route branch.
- \`tools/vision_tools.py\`: \`vision_analyze_tool\` may write temporary media, perform retries and emit debug records.

There is currently **no connection** between this probe library and the installed vendor gateway. CI passing proves only the offline fixture and mocked boundary. It does not prove any running service/config, OpenRouter account billing, private data restrictions or that user images are filtered in the Gateway. The previously accepted content scope remains **public or genuinely synthetic images only**. The OpenRouter account ZDR policy was relaxed independently and is account-wide, so it **does not enforce that content scope**.

## Required future integration gates

1. **Source owner and provenance:** bind exact installed Hermes revision and relevant file hashes. Confirm the Gateway's real ingress path, actual image-routing decision, provider client and true last outbound transport. No raw app config, secrets, process environment, session DB, personal media or private paths are needed for source ownership proof.
2. **Production-safe implementation (separate scope):** integrate an allowlist at the **actual inbound media boundary**, not merely in a test harness or an LLM prompt. Enforce exactly one synthetic image and the exact free NVIDIA route, block native/paid/fallback paths, and apply a transport-level request counter with internal SDK retries disabled. Do not rely on a single call to a higher-level Hermes vision tool.
3. **Enumerate side effects:** vendor temp/cache/debug files; Gateway message/session data; transport replies; model requests; API price caps. Specify explicit owner LIVE authority for every real mutation or external provider call. Prefer separate isolated/offline tests of the installed source before a LIVE exercise.
4. **Later LIVE gate:** one frozen fixture, exact host/Gateway/installed SHA, exact method and expected config identity, hard cap **one outbound API attempt**, price cap zero, no retries/restart/rollback, and sanitized PASS/STOP. STOP before first mutation for any uncertainty; after mutation or tool error, read-only evidence and STOP, no unapproved cleanup.

**Outcome of issue #1334:** offline fixture and callback-boundary tests only. **Gateway LIVE vision acceptance remains NOT VERIFIED.**
